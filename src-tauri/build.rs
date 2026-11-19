fn main() {
    println!("cargo:rerun-if-changed=tauri.conf.json");
    println!("cargo:rerun-if-changed=icons/icon.png");
    println!("cargo:rerun-if-changed=icons/icon.icns");
    println!("cargo:rerun-if-changed=icons/128x128@2x.png");
    // `bundle.resources` must exist; `just bundle-agent` fills it for release builds.
    std::fs::create_dir_all("../agent/dist/python").expect("create agent/dist/python");
    tauri_build::build()
}
