// structquery: pybind11 binding around Indri's QueryEnvironment and IndexEnvironment.
// Kept deliberately thin: type conversion, GIL release, and exception translation only.
// All retrieval, parsing, tokenizing and stemming is done by unmodified Indri code.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "indri/IndexEnvironment.hpp"
#include "indri/QueryEnvironment.hpp"
#include "indri/QueryParserFactory.hpp"
#include "indri/SnippetBuilder.hpp"
#include "indri/indri-platform.h"
#include "lemur/Exception.hpp"

namespace py = pybind11;

namespace {

PyObject* g_indri_error = nullptr;
PyObject* g_syntax_error = nullptr;

const char kParsePrefix[] = "Couldn't understand this query";

// Thrown by us for query-syntax problems so they map to QuerySyntaxError.
struct SyntaxError {
  std::string message;
};

std::string metadata_value(const indri::parse::MetadataPair& p) {
  const char* v = static_cast<const char*>(p.value);
  if (!v || p.valueLength <= 0) return std::string();
  return std::string(v, strnlen(v, static_cast<size_t>(p.valueLength)));
}

struct DocumentsHolder {
  std::vector<indri::api::ParsedDocument*> docs;
  ~DocumentsHolder() {
    for (auto* d : docs) delete d;
  }
};

py::dict document_to_dict(const indri::api::ParsedDocument* d) {
  py::dict out;
  py::dict meta;
  for (size_t i = 0; i < d->metadata.size(); ++i) {
    const auto& p = d->metadata[i];
    if (p.key) meta[py::str(p.key)] = py::bytes(metadata_value(p));
  }
  out["metadata"] = meta;
  out["content"] = py::bytes(d->content ? std::string(d->content, d->contentLength) : std::string());
  size_t n = d->textLength;
  if (d->text && n > 0 && d->text[n - 1] == '\0') --n;
  out["raw"] = py::bytes(d->text ? std::string(d->text, n) : std::string());
  return out;
}

class Index {
 public:
  Index(const std::string& path, const std::vector<std::string>& rules, long long memory)
      : path_(path), env_(new indri::api::QueryEnvironment()) {
    if (memory > 0) env_->setMemory(static_cast<UINT64>(memory));
    env_->addIndex(path);
    if (!rules.empty()) env_->setScoringRules(rules);
  }
  ~Index() { close(); }

  void close() {
    if (env_) {
      try {
        env_->close();
      } catch (...) {
      }
      env_.reset();
    }
  }
  bool closed() const { return !env_; }

  indri::api::QueryEnvironment& env() {
    if (!env_) throw std::runtime_error("index is closed");
    return *env_;
  }

  static void validate(const std::string& query) {
    std::unique_ptr<indri::api::QueryParserWrapper> parser(
        indri::api::QueryParserFactory::get(query, "indri"));
    try {
      parser->query();
    } catch (antlr::ANTLRException& e) {
      throw SyntaxError{std::string(kParsePrefix) + ": " + e.getMessage()};
    }
  }

  // Returns [(docno, score, internal_id, begin, end)], best first.
  py::list search(const std::string& query, int k) {
    std::vector<indri::api::ScoredExtentResult> res;
    std::vector<std::string> names;
    {
      py::gil_scoped_release nogil;
      res = env().runQuery(query, k);
      if (!res.empty()) names = env().documentMetadata(res, "docno");
    }
    py::list out;
    for (size_t i = 0; i < res.size(); ++i) {
      out.append(py::make_tuple(py::bytes(i < names.size() ? names[i] : std::string()),
                                res[i].score, static_cast<long long>(res[i].document),
                                res[i].begin, res[i].end));
    }
    return out;
  }

  // Same as search() plus stored document and an Indri-built text snippet per hit.
  py::list search_docs(const std::string& query, int k, bool snippets) {
    std::unique_ptr<indri::api::QueryAnnotation> annotation;
    std::vector<indri::api::ScoredExtentResult> res;
    std::vector<std::string> names;
    DocumentsHolder holder;
    {
      py::gil_scoped_release nogil;
      annotation.reset(env().runAnnotatedQuery(query, k));
      res = annotation->getResults();
      if (!res.empty()) {
        names = env().documentMetadata(res, "docno");
        holder.docs = env().documents(res);
      }
    }
    indri::api::SnippetBuilder builder(false);
    py::list out;
    for (size_t i = 0; i < res.size(); ++i) {
      py::object doc = py::none();
      py::object snip = py::none();
      if (i < holder.docs.size() && holder.docs[i]) {
        doc = document_to_dict(holder.docs[i]);
        if (snippets)
          snip = py::bytes(builder.build(res[i].document, holder.docs[i], annotation.get()));
      }
      out.append(py::make_tuple(py::bytes(i < names.size() ? names[i] : std::string()),
                                res[i].score, static_cast<long long>(res[i].document),
                                res[i].begin, res[i].end, doc, snip));
    }
    return out;
  }

  std::vector<long long> internal_ids(const std::vector<std::string>& docnos) {
    std::vector<long long> out;
    for (const auto& d : docnos) {
      std::vector<std::string> one(1, d);
      auto ids = env().documentIDsFromMetadata("docno", one);
      out.push_back(ids.empty() ? 0 : static_cast<long long>(ids[0]));
    }
    return out;
  }

  py::list documents(const std::vector<long long>& ids) {
    std::vector<lemur::api::DOCID_T> v(ids.begin(), ids.end());
    DocumentsHolder holder;
    holder.docs = env().documents(v);
    py::list out;
    for (auto* d : holder.docs) {
      if (d) out.append(document_to_dict(d));
      else out.append(py::none());
    }
    return out;
  }

  std::vector<py::bytes> docnos(const std::vector<long long>& ids) {
    std::vector<lemur::api::DOCID_T> v(ids.begin(), ids.end());
    std::vector<py::bytes> out;
    for (auto& s : env().documentMetadata(v, "docno")) out.emplace_back(s);
    return out;
  }

  long long document_count() { return env().documentCount(); }
  long long document_count_term(const std::string& t) { return env().documentCount(t); }
  long long document_stem_count(const std::string& t) { return env().documentStemCount(t); }
  long long term_count() { return env().termCount(); }
  long long term_count_unique() { return env().termCountUnique(); }
  long long term_count_term(const std::string& t) { return env().termCount(t); }
  long long stem_count(const std::string& t) { return env().stemCount(t); }
  long long term_field_count(const std::string& t, const std::string& f) {
    return env().termFieldCount(t, f);
  }
  double expression_count(const std::string& e) {
    py::gil_scoped_release nogil;
    return env().expressionCount(e);
  }
  double document_expression_count(const std::string& e) {
    py::gil_scoped_release nogil;
    return env().documentExpressionCount(e);
  }
  int document_length(long long id) {
    return env().documentLength(static_cast<lemur::api::DOCID_T>(id));
  }
  std::vector<std::string> field_list() { return env().fieldList(); }
  py::bytes stem_term(const std::string& t) { return py::bytes(env().stemTerm(t)); }
  const std::string& path() const { return path_; }

 private:
  std::string path_;
  std::unique_ptr<indri::api::QueryEnvironment> env_;
};

class Builder {
 public:
  Builder() : env_(new indri::api::IndexEnvironment()), open_(false) {}
  ~Builder() { close(); }

  indri::api::IndexEnvironment& env() {
    if (!env_) throw std::runtime_error("index builder is closed");
    return *env_;
  }

  void set_memory(long long bytes) { env().setMemory(static_cast<UINT64>(bytes)); }
  void set_stemmer(const std::string& name) { env().setStemmer(name); }
  void set_stopwords(const std::vector<std::string>& words) { env().setStopwords(words); }
  // Mirrors what IndriBuildIndex does for <field> parameters: register the fields, then add
  // them to the "index" tag list of every file class so the parsers emit them as extents.
  void set_indexed_fields(const std::vector<std::string>& names,
                          const std::vector<std::string>& file_classes) {
    env().setIndexedFields(names);
    for (const auto& cls : file_classes) {
      std::unique_ptr<indri::parse::FileClassEnvironmentFactory::Specification> spec(
          env().getFileClassSpec(cls));
      if (!spec) continue;
      bool changed = false;
      for (const auto& n : names) {
        if (std::find(spec->index.begin(), spec->index.end(), n) == spec->index.end()) {
          spec->index.push_back(n);
          changed = true;
          if (!spec->include.empty() &&
              std::find(spec->include.begin(), spec->include.end(), n) == spec->include.end())
            spec->include.push_back(n);
        }
      }
      if (changed) env().addFileClass(*spec);
    }
  }
  void set_numeric_field(const std::string& name, bool numeric) {
    env().setNumericField(name, numeric);
  }
  void set_metadata_indexed_fields(const std::vector<std::string>& forward,
                                   const std::vector<std::string>& backward) {
    env().setMetadataIndexedFields(forward, backward);
  }
  void set_store_docs(bool flag) { env().setStoreDocs(flag); }
  void set_normalization(bool flag) { env().setNormalization(flag); }

  // After a failed create()/open() Indri's IndexEnvironment is left half-initialised and its
  // destructor crashes, so on failure the object is deliberately leaked instead of destroyed.
  void create(const std::string& path) {
    try {
      env().create(path);
    } catch (...) {
      (void)env_.release();
      throw;
    }
    open_ = true;
  }
  void open(const std::string& path) {
    try {
      env().open(path);
    } catch (...) {
      (void)env_.release();
      throw;
    }
    open_ = true;
  }
  void close() {
    if (env_) {
      if (open_) {
        py::gil_scoped_release nogil;
        env_->close();
      }
      open_ = false;
      env_.reset();
    }
  }

  long long add_string(const std::string& text, const std::string& file_class,
                       const std::vector<std::pair<std::string, std::string>>& metadata) {
    std::vector<indri::parse::MetadataPair> pairs;
    pairs.reserve(metadata.size());
    for (const auto& kv : metadata) {
      indri::parse::MetadataPair p;
      p.key = kv.first.c_str();
      p.value = kv.second.c_str();
      p.valueLength = static_cast<int>(kv.second.size() + 1);
      pairs.push_back(p);
    }
    py::gil_scoped_release nogil;
    return static_cast<long long>(env().addString(text, file_class, pairs));
  }

  void add_file(const std::string& path, const std::string& file_class) {
    py::gil_scoped_release nogil;
    if (file_class.empty()) env().addFile(path);
    else env().addFile(path, file_class);
  }

  int documents_indexed() { return env().documentsIndexed(); }
  int documents_seen() { return env().documentsSeen(); }

 private:
  std::unique_ptr<indri::api::IndexEnvironment> env_;
  bool open_;
};

}  // namespace

PYBIND11_MODULE(_structquery, m) {
  m.doc() = "Low-level Indri binding. Use the `structquery` package API instead.";
  m.attr("INDRI_VERSION") = INDRI_DISTRIBUTION;

  g_indri_error = PyErr_NewExceptionWithDoc(
      "structquery.IndriError", "Any error reported by the Indri engine.", PyExc_RuntimeError, nullptr);
  g_syntax_error = PyErr_NewExceptionWithDoc(
      "structquery.QuerySyntaxError", "The query is not valid Indri query language.", g_indri_error,
      nullptr);
  m.add_object("IndriError", py::reinterpret_borrow<py::object>(g_indri_error));
  m.add_object("QuerySyntaxError", py::reinterpret_borrow<py::object>(g_syntax_error));

  py::register_exception_translator([](std::exception_ptr p) {
    try {
      if (p) std::rethrow_exception(p);
    } catch (const SyntaxError& e) {
      PyErr_SetString(g_syntax_error, e.message.c_str());
    } catch (const lemur::api::Exception& e) {
      const std::string& what = e.what();
      bool syntax = what.find(kParsePrefix) != std::string::npos;
      PyErr_SetString(syntax ? g_syntax_error : g_indri_error, what.c_str());
    } catch (antlr::ANTLRException& e) {
      PyErr_SetString(g_syntax_error, (std::string(kParsePrefix) + ": " + e.getMessage()).c_str());
    }
  });

  py::class_<Index>(m, "Index")
      .def(py::init<const std::string&, const std::vector<std::string>&, long long>(),
           py::arg("path"), py::arg("rules") = std::vector<std::string>(), py::arg("memory") = 0)
      .def("close", &Index::close)
      .def_property_readonly("closed", &Index::closed)
      .def_property_readonly("path", &Index::path)
      .def_static("validate", &Index::validate)
      .def("search", &Index::search)
      .def("search_docs", &Index::search_docs)
      .def("internal_ids", &Index::internal_ids)
      .def("documents", &Index::documents)
      .def("docnos", &Index::docnos)
      .def("document_count", &Index::document_count)
      .def("document_count_term", &Index::document_count_term)
      .def("document_stem_count", &Index::document_stem_count)
      .def("term_count", &Index::term_count)
      .def("term_count_unique", &Index::term_count_unique)
      .def("term_count_term", &Index::term_count_term)
      .def("stem_count", &Index::stem_count)
      .def("term_field_count", &Index::term_field_count)
      .def("expression_count", &Index::expression_count)
      .def("document_expression_count", &Index::document_expression_count)
      .def("document_length", &Index::document_length)
      .def("field_list", &Index::field_list)
      .def("stem_term", &Index::stem_term);

  py::class_<Builder>(m, "Builder")
      .def(py::init<>())
      .def("set_memory", &Builder::set_memory)
      .def("set_stemmer", &Builder::set_stemmer)
      .def("set_stopwords", &Builder::set_stopwords)
      .def("set_indexed_fields", &Builder::set_indexed_fields)
      .def("set_numeric_field", &Builder::set_numeric_field)
      .def("set_metadata_indexed_fields", &Builder::set_metadata_indexed_fields)
      .def("set_store_docs", &Builder::set_store_docs)
      .def("set_normalization", &Builder::set_normalization)
      .def("create", &Builder::create)
      .def("open", &Builder::open)
      .def("close", &Builder::close)
      .def("add_string", &Builder::add_string)
      .def("add_file", &Builder::add_file, py::arg("path"), py::arg("file_class") = "")
      .def("documents_indexed", &Builder::documents_indexed)
      .def("documents_seen", &Builder::documents_seen);
}
