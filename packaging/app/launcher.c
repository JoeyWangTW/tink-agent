/* Tink Agent.app main executable.
 *
 * Embeds Python in-process instead of exec'ing the framework interpreter, so
 * the running process *is* the app bundle: it joins the GUI session (menu-bar
 * icon draws) and macOS attributes Microphone/Accessibility to "Tink Agent"
 * rather than to Python.app.
 *
 * Paths are read from Info.plist (written by packaging/build_app.sh):
 *   TinkAgentRepo    - checkout containing the tink_agent package
 *   TinkAgentPython  - venv interpreter whose site-packages to use
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <CoreFoundation/CoreFoundation.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>

static int plist_string(const char *key, char *out, size_t n) {
    CFBundleRef bundle = CFBundleGetMainBundle();
    if (!bundle) return 0;
    CFStringRef k = CFStringCreateWithCString(NULL, key, kCFStringEncodingUTF8);
    CFTypeRef v = CFBundleGetValueForInfoDictionaryKey(bundle, k);
    CFRelease(k);
    if (!v || CFGetTypeID(v) != CFStringGetTypeID()) return 0;
    return CFStringGetCString((CFStringRef)v, out, (CFIndex)n, kCFStringEncodingUTF8);
}

static void fail(const char *msg, PyStatus st) {
    fprintf(stderr, "Tink Agent launcher: %s%s%s\n", msg,
            st.err_msg ? ": " : "", st.err_msg ? st.err_msg : "");
    exit(1);
}

int main(int argc, char **argv) {
    char repo[PATH_MAX], python[PATH_MAX], self[PATH_MAX];
    uint32_t self_len = sizeof(self);
    if (!plist_string("TinkAgentRepo", repo, sizeof repo) ||
        !plist_string("TinkAgentPython", python, sizeof python)) {
        fprintf(stderr, "Tink Agent launcher: TinkAgentRepo/TinkAgentPython missing "
                        "from Info.plist; rebuild with packaging/build_app.sh\n");
        return 1;
    }
    /* Lets tink_agent point "Start at login" at this executable. */
    if (_NSGetExecutablePath(self, &self_len) == 0)
        setenv("TINK_AGENT_APP_EXEC", self, 1);
    setenv("PYTHONUNBUFFERED", "1", 1);
    /* Make the checkout importable regardless of how we were launched
       (prepended to sys.path; stdlib + venv paths are still computed). */
    setenv("PYTHONPATH", repo, 1);
    if (chdir(repo) != 0) perror("Tink Agent launcher: chdir");

    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    PyStatus st;
    /* Pointing `executable` at the venv interpreter makes Python find its
       pyvenv.cfg and use the venv's site-packages. */
    st = PyConfig_SetBytesString(&config, &config.executable, python);
    if (PyStatus_Exception(st)) fail("executable", st);
    st = PyConfig_SetBytesString(&config, &config.run_module, "tink_agent");
    if (PyStatus_Exception(st)) fail("run_module", st);
    st = PyConfig_SetBytesArgv(&config, argc, argv);
    if (PyStatus_Exception(st)) fail("argv", st);

    st = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(st)) Py_ExitStatusException(st);
    return Py_RunMain();
}
