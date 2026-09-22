# Third-Party Notices

NASDrop includes the following third-party components. Each component remains subject to its own license terms.

## Node.js 22.13.1

- Project: [Node.js](https://nodejs.org/)
- Source release: [v22.13.1](https://github.com/nodejs/node/tree/v22.13.1)
- Binary distribution: [`nodejs/unofficial-builds`](https://github.com/nodejs/unofficial-builds), `linux-x64-glibc-217`
- Use in NASDrop: the glibc 2.17-compatible Linux x64 Node.js runtime bundled in the SPK to execute `gofile_wt.mjs` on supported DSM 7 systems
- License text in this repository: [`synology/licenses/nodejs-LICENSE.txt`](synology/licenses/nodejs-LICENSE.txt)
- License text in the installed package: `licenses/nodejs-LICENSE.txt`

The Node.js license file also contains the notices required by third-party software distributed with Node.js.

## 7-Zip 26.02

NASDrop's Synology x86_64 package includes the official 7-Zip Linux console executable (`7zz`) to extract ZIP, 7z, RAR, and related archive formats.

- Upstream: https://www.7-zip.org/
- Source and releases: https://github.com/ip7z/7zip
- Bundled archive: `7z2602-linux-x64.tar.xz`
- SHA-256: `41aaba7b1235304ab5aa0624530c67ae829496cd29e875925271efdccc28c03e`
- Installed license: `7zip-LICENSE.txt`

7-Zip is primarily licensed under the GNU LGPL, with BSD-licensed components and an unRAR restriction for portions of the RAR code. The verbatim upstream `License.txt` is included in the SPK.

## 7-Zip 26.03 (Docker)

NASDrop's Docker image installs the official 7-Zip Linux console executable during the image build. The image selects the archive by Docker target architecture, verifies it before extraction, and installs the upstream `License.txt` at `/usr/share/doc/7zip/License.txt`.

- Upstream release: https://github.com/ip7z/7zip/releases/tag/26.03
- AMD64 archive: `7z2603-linux-x64.tar.xz`
- AMD64 SHA-256: `dc99eff5008f1ab79bd7084c68513701547a808a89502bf4133683535ab3c695`
- ARM64 archive: `7z2603-linux-arm64.tar.xz`
- ARM64 SHA-256: `2389ba20e4d8295e8709c20b6263b69bd1ec4972fe38a04ad7a1badbf595b996`

The Docker build fails if the checksum does not match or the resulting executable does not advertise both RAR and RAR5 read support.

NASDrop's own license is available in [`LICENSE`](LICENSE) and is also included in the SPK.
