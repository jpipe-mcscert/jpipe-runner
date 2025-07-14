require "formula"

class $CLASS_NAME < Formula
  include Language::Python::Virtualenv

  homepage "$HOMEPAGE_URL"
  url "$SOURCE_URL"
  sha256 "$SOURCE_SHA256"

  depends_on "python@$PYTHON_VERSION"
  depends_on "python-tk@$PYTHON_VERSION"
  depends_on "libjpeg-turbo"
  depends_on "freetype"

$RESOURCES

  def install
    venv = virtualenv_create(libexec, "python$PYTHON_VERSION")
    venv.pip_install resources
    venv.pip_install_and_link buildpath
  end
end
