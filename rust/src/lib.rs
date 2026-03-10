use std::ffi::{c_char, CStr, CString};
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::{Mutex, OnceLock};

static QUEUE_COUNT: AtomicI32 = AtomicI32::new(0);
static VERSION_BYTES: &[u8] = b"SpellVision Core 0.2.0\0";
static LAST_SUMMARY: OnceLock<Mutex<CString>> = OnceLock::new();

#[derive(Clone, Debug)]
struct JobRecord {
    id: i32,
    task_type: String,
    prompt: String,
    output_path: String,
    status: String,
}

static JOBS: OnceLock<Mutex<Vec<JobRecord>>> = OnceLock::new();
static NEXT_JOB_ID: AtomicI32 = AtomicI32::new(1);

fn jobs() -> &'static Mutex<Vec<JobRecord>> {
    JOBS.get_or_init(|| Mutex::new(Vec::new()))
}

fn last_summary_buf() -> &'static Mutex<CString> {
    LAST_SUMMARY.get_or_init(|| Mutex::new(CString::new("No jobs yet").unwrap()))
}

#[no_mangle]
pub extern "C" fn spellvision_version() -> *const c_char {
    VERSION_BYTES.as_ptr() as *const c_char
}

#[no_mangle]
pub extern "C" fn spellvision_queue_count() -> i32 {
    QUEUE_COUNT.load(Ordering::Relaxed)
}

#[no_mangle]
pub extern "C" fn spellvision_add_dummy_job() {
    let id = NEXT_JOB_ID.fetch_add(1, Ordering::Relaxed);
    let mut lock = jobs().lock().unwrap();
    lock.push(JobRecord {
        id,
        task_type: "dummy".to_string(),
        prompt: "dummy".to_string(),
        output_path: String::new(),
        status: "queued".to_string(),
    });
    QUEUE_COUNT.fetch_add(1, Ordering::Relaxed);
}

#[no_mangle]
pub extern "C" fn spellvision_create_t2i_job(
    prompt: *const c_char,
    output_path: *const c_char,
) -> i32 {
    if prompt.is_null() || output_path.is_null() {
        return -1;
    }

    let prompt_str = unsafe { CStr::from_ptr(prompt) }
        .to_string_lossy()
        .to_string();

    let output_str = unsafe { CStr::from_ptr(output_path) }
        .to_string_lossy()
        .to_string();

    let id = NEXT_JOB_ID.fetch_add(1, Ordering::Relaxed);

    let mut lock = jobs().lock().unwrap();
    lock.push(JobRecord {
        id,
        task_type: "t2i".to_string(),
        prompt: prompt_str,
        output_path: output_str,
        status: "queued".to_string(),
    });

    QUEUE_COUNT.fetch_add(1, Ordering::Relaxed);
    id
}

#[no_mangle]
pub extern "C" fn spellvision_mark_job_finished(job_id: i32) {
    let mut lock = jobs().lock().unwrap();
    if let Some(job) = lock.iter_mut().find(|j| j.id == job_id) {
        job.status = "finished".to_string();
    }
    QUEUE_COUNT.fetch_sub(1, Ordering::Relaxed);
}

#[no_mangle]
pub extern "C" fn spellvision_mark_job_failed(job_id: i32) {
    let mut lock = jobs().lock().unwrap();
    if let Some(job) = lock.iter_mut().find(|j| j.id == job_id) {
        job.status = "failed".to_string();
    }
    QUEUE_COUNT.fetch_sub(1, Ordering::Relaxed);
}

#[no_mangle]
pub extern "C" fn spellvision_last_job_summary() -> *const c_char {
    let lock = jobs().lock().unwrap();
    let summary = if let Some(job) = lock.last() {
        format!(
            "Job #{}, type={}, status={}, prompt=\"{}\", output={}",
            job.id, job.task_type, job.status, job.prompt, job.output_path
        )
    } else {
        "No jobs yet".to_string()
    };
    drop(lock);

    let safe_cstring = CString::new(summary)
        .unwrap_or_else(|_| CString::new("summary error").unwrap());

    let mut summary_lock = last_summary_buf().lock().unwrap();
    *summary_lock = safe_cstring;
    summary_lock.as_ptr()
}