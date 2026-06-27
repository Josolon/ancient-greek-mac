# 🏛️ macOS Ancient Greek Dictionary

A custom `.dictionary` plugin for the native macOS Dictionary app and system-wide "Look Up" feature. This dictionary combines complete entries from the LSJ with interactive, collapsible morphology tables for noun declensions and verb principal parts.

## ✨ Features

* **System Integration:** Works natively with macOS "Look Up" (Force Click or Three-Finger Tap on any word).
* **Collapsible Morphology:** Utilizes native HTML5 `<details>` tags so declensions and principal parts stay folded and hidden until you need them, keeping the main entry clean.
* **Polytonic Support:** Designed to handle Greek diacritics smoothly within Apple's search engine.

## 📦 Installation (For End Users)

1. Download the latest `AncientGreek.dictionary.zip` from the [Releases](link-to-releases) page.
2. Unzip the file.
3. Open Finder, press `Cmd + Shift + G`, and go to `~/Library/Dictionaries/`.
4. Drag and drop the `AncientGreek.dictionary` file into this folder.
5. Open the macOS **Dictionary app**, go to **Settings**, and check the box next to "Ancient Greek" to enable it.

## 🛠️ Building from Source

If you want to modify the dictionary data or compile it yourself, you will need Xcode's Additional Tools.

### Prerequisites
* Python 3.x
* [Dictionary Development Kit](https://developer.apple.com/download/all/) (Found in Apple's "Additional Tools for Xcode").

### Build Instructions
1. Clone this repository: `git clone https://github.com/yourusername/macOS-Greek-Dictionary.git`
2. Run the Python generation script to build the XML:
   ```bash
   python3 scripts/build_xml.py
   ```
3. Navigate to the src folder and run make:
   ```bash
    cd src
    make
    make install
   ```
## 🤝 Contributing
Contributions are welcome! If you want to improve the CSS styling, refine the Python parsing script, or map better morphology data, please submit a pull request.
