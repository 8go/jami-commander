# PRE-INSTALLATION

Before you install `matrix-commander` with `pip install matrix-commander`
you *must* have followed these prerequisites steps! Otherwise `pip` will fail.

- Note that even if you install via `pip` you must have a) Python 3.11+
  and b) `libolm` installed.
- Run `python -V` to get your Python version number and assure that it is
  3.11+.
- For e2ee support, python-olm is needed which requires the libolm C
  library (version 3.x). See also https://gitlab.matrix.org/matrix-org/olm.
  Make sure that version 3 is installed. Version 2 will not work.
  To install `libolm` do this:
  - On Debian, Ubuntu and Debian/Ubuntu derivative distributions: `sudo apt install libolm-dev`
  - On Fedora or Fedora derivative distributions do: `sudo dnf install libolm-devel`
  - On MacOS use brew: `brew install libolm`
