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

  def install
    virtualenv_install_with_resources
  end

  def post_install
    ohai "Verifying installation..."
    system bin/"jpipe-runner", "--help"
    ohai "should be working"
  rescue
    odie "will not work. have you updated python deps? RTFM."
  end
end
