# Third-party notices

structquery's own code (everything outside `third_party/`) is under the MIT licence in `LICENSE`.

Source and binary distributions of structquery include the Indri 5.21 search engine from the
Lemur Project (University of Massachusetts Amherst and Carnegie Mellon University), which is
under its own licence: `third_party/indri/LICENSE.txt`. That licence must stay with any copy,
including compiled wheels. The Indri distribution in turn bundles ANTLR, xpdf and zlib sources
under `third_party/indri/contrib/`, each with its own notice (`README.antlr`, `README.xpdf`,
`README.zlib`).

The Indri source is unmodified except for the patches in `third_party/patches/`.

structquery is not a Lemur Project product and is not endorsed by the Lemur Project, the
University of Massachusetts or Carnegie Mellon University.
