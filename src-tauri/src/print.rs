//! Save an artifact as PDF: open the page in its own window and show the print dialog,
//! whose "Save as PDF" (macOS) or "Microsoft Print to PDF" (Windows) writes the file.
//!
//! The page is model-written HTML with scripts. Its window is not in any capability, so it
//! gets no IPC commands, and its origin is `thea-print`, not the app's.

use std::collections::HashMap;
use std::sync::Mutex;
use tauri::http::{Request, Response};
use tauri::webview::PageLoadEvent;
use tauri::{
    AppHandle, Manager, Runtime, State, UriSchemeContext, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};

pub const SCHEME: &str = "thea-print";

/// Page margin on every side, in points (72 per inch): about 18 mm.
#[cfg(target_os = "macos")]
const MARGIN_PT: f64 = 51.0;

/// Pages waiting for their window to load them, by id. Each is served once.
#[derive(Default)]
pub struct PrintPages(Mutex<HashMap<String, String>>);

pub fn serve<R: Runtime>(ctx: UriSchemeContext<'_, R>, req: Request<Vec<u8>>) -> Response<Vec<u8>> {
    let id = req.uri().path().trim_start_matches('/');
    let page = ctx
        .app_handle()
        .state::<PrintPages>()
        .0
        .lock()
        .map(|mut pages| pages.remove(id))
        .unwrap_or_default();
    match page {
        Some(html) => Response::builder()
            .header("Content-Type", "text/html; charset=utf-8")
            .body(html.into_bytes()),
        None => Response::builder().status(404).body(Vec::new()),
    }
    .expect("static response parts are valid")
}

fn page_url(id: &str) -> String {
    // Windows' WebView2 serves custom schemes as http://<scheme>.localhost.
    if cfg!(windows) {
        format!("http://{SCHEME}.localhost/{id}")
    } else {
        format!("{SCHEME}://localhost/{id}")
    }
}

/// Show the print dialog for `w`. `name` is the suggested PDF file name, without `.pdf`.
#[cfg(target_os = "macos")]
fn print_page<R: Runtime>(w: &WebviewWindow<R>, name: String) {
    // Tauri's print() sets every margin to 0 and names the PDF after the window title.
    let _ = w.with_webview(move |pw| unsafe {
        use objc2_app_kit::{NSPrintInfo, NSWindow};
        use objc2_foundation::NSString;
        use objc2_web_kit::WKWebView;
        let view = &*pw.inner().cast::<WKWebView>();
        let window = &*pw.ns_window().cast::<NSWindow>();
        let info = NSPrintInfo::sharedPrintInfo();
        info.setTopMargin(MARGIN_PT);
        info.setBottomMargin(MARGIN_PT);
        info.setLeftMargin(MARGIN_PT);
        info.setRightMargin(MARGIN_PT);
        let op = view.printOperationWithPrintInfo(&info);
        op.setJobTitle(Some(&NSString::from_str(&name)));
        op.setCanSpawnSeparateThread(true);
        op.runOperationModalForWindow_delegate_didRunSelector_contextInfo(
            window,
            None,
            None,
            std::ptr::null_mut(),
        );
    });
}

/// WebView2 uses its own margins and names the PDF after the page's `<title>`.
#[cfg(not(target_os = "macos"))]
fn print_page<R: Runtime>(w: &WebviewWindow<R>, _name: String) {
    let _ = w.print();
}

#[tauri::command]
pub fn print_artifact(
    app: AppHandle,
    pages: State<'_, PrintPages>,
    title: String,
    html: String,
) -> Result<(), String> {
    let id = uuid::Uuid::new_v4().to_string();
    let url = page_url(&id).parse().map_err(|e| format!("{e}"))?;
    pages
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .insert(id.clone(), html);
    WebviewWindowBuilder::new(&app, format!("print-{id}"), WebviewUrl::External(url))
        .title(&title)
        .inner_size(860.0, 1000.0)
        .on_page_load(move |w, p| {
            if p.event() == PageLoadEvent::Finished {
                print_page(&w, title.clone());
            }
        })
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}
