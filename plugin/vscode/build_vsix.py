"""Packs the Compass Review extension into a `.vsix` beside its sources.

    python plugin/vscode/build_vsix.py

The archive is `compass-review/compass-review-<version>.vsix`, the layout
`code --install-extension` reads: `[Content_Types].xml`, `extension.vsixmanifest`
and the extension's files under `extension/`. Line endings in the packed files
are normalised to LF and the archive's timestamps are fixed, so packing the
same sources twice gives the same bytes. Any other `.vsix` in the folder is
removed, so exactly one ships, carrying the current sources.
"""

import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

EXTENSION_DIR = Path(__file__).resolve().parent / "compass-review"
PACKED_FILES = (
    "package.json",
    "extension.js",
    "media/card.js",
    "media/card.css",
    "media/icon.svg",
)
CONTENT_TYPES = {
    ".json": "application/json",
    ".js": "application/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".vsixmanifest": "text/xml",
}
STAMP = (2020, 1, 1, 0, 0, 0)


def read_package(folder):
    return json.loads((folder / "package.json").read_text(encoding="utf-8"))


def content_types():
    defaults = "".join(
        f'<Default Extension={quoteattr(ext)} ContentType={quoteattr(kind)}/>' for ext, kind in CONTENT_TYPES.items()
    )
    return f'<?xml version="1.0" encoding="utf-8"?>\n<Types>{defaults}</Types>\n'


def manifest(package):
    def prop(name, value):
        return f"      <Property Id={quoteattr(name)} Value={quoteattr(value)} />\n"

    engine = package["engines"]["vscode"]
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" '
        'xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">\n'
        "  <Metadata>\n"
        f"    <Identity Language=\"en-US\" Id={quoteattr(package['name'])} Version={quoteattr(package['version'])} "
        f"Publisher={quoteattr(package['publisher'])} />\n"
        f"    <DisplayName>{escape(package.get('displayName', package['name']))}</DisplayName>\n"
        f"    <Description xml:space=\"preserve\">{escape(package.get('description', ''))}</Description>\n"
        f"    <Categories>{escape(','.join(package.get('categories', ['Other'])))}</Categories>\n"
        "    <GalleryFlags>Public</GalleryFlags>\n"
        "    <Properties>\n"
        + prop("Microsoft.VisualStudio.Code.Engine", engine)
        + prop("Microsoft.VisualStudio.Code.ExtensionDependencies", "")
        + prop("Microsoft.VisualStudio.Code.ExtensionPack", "")
        + prop("Microsoft.VisualStudio.Code.ExtensionKind", "workspace")
        + prop("Microsoft.VisualStudio.Code.LocalizedLanguages", "")
        + prop("Microsoft.VisualStudio.Code.ExecutesCode", "true")
        + "    </Properties>\n"
        "  </Metadata>\n"
        "  <Installation>\n"
        '    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>\n'
        "  </Installation>\n"
        "  <Dependencies/>\n"
        "  <Assets>\n"
        '    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />\n'
        "  </Assets>\n"
        "</PackageManifest>\n"
    )


def add(archive, name, data):
    info = zipfile.ZipInfo(name, STAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def build(folder=EXTENSION_DIR):
    """Pack `folder`; returns the path of the `.vsix`, the only one left in
    `folder`."""
    folder = Path(folder)
    package = read_package(folder)
    target = folder / f"{package['name']}-{package['version']}.vsix"
    staged = target.with_suffix(".vsix.tmp")
    with zipfile.ZipFile(staged, "w") as archive:
        add(archive, "[Content_Types].xml", content_types().encode("utf-8"))
        add(archive, "extension.vsixmanifest", manifest(package).encode("utf-8"))
        for name in PACKED_FILES:
            add(archive, f"extension/{name}", (folder / name).read_bytes().replace(b"\r\n", b"\n"))
    staged.replace(target)
    for old in folder.glob("*.vsix"):
        if old != target:
            old.unlink()
    return target


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else EXTENSION_DIR))
