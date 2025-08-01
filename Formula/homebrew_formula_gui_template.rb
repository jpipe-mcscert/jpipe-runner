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
    depends_on "graphviz"

    $RESOURCES

    def install
    ENV["SOURCE_DATE_EPOCH"] = Time.now.to_i.to_s
    virtualenv_install_with_resources
    end

    def post_install
      ohai "Verifying #{name} installation by checking command availability..."
      system bin/"jpipe-runner", "--help"
      ohai "#{name} installation verified successfully"
    rescue
      odie "#{name} verification failed. Please check Python dependencies and ensure all requirements are installed correctly."
    end
end
