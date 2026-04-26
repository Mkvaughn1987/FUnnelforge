"""C13: CoInitialize / CoUninitialize must be balanced. We mock pythoncom
to count calls and verify the scanner does both."""
import sys
import types


def test_outlook_monitor_scan_balances_co_init(monkeypatch):
    counts = {"init": 0, "uninit": 0}

    fake_pythoncom = types.ModuleType("pythoncom")
    def _init():
        counts["init"] += 1
    def _uninit():
        counts["uninit"] += 1
    fake_pythoncom.CoInitialize = _init
    fake_pythoncom.CoUninitialize = _uninit
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    fake_win32 = types.ModuleType("win32com")
    fake_win32_client = types.ModuleType("win32com.client")
    fake_win32_dynamic = types.ModuleType("win32com.client.dynamic")
    def _dispatch(_):
        class _Ol:
            def GetNamespace(self, _name):
                raise RuntimeError("stop here")
        return _Ol()
    fake_win32_dynamic.Dispatch = _dispatch
    fake_win32_client.dynamic = fake_win32_dynamic
    fake_win32.client = fake_win32_client
    monkeypatch.setitem(sys.modules, "win32com", fake_win32)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_win32_client)
    monkeypatch.setitem(sys.modules, "win32com.client.dynamic", fake_win32_dynamic)

    import flowdrip_app as fa
    mon = fa.OutlookMonitor()
    try:
        mon._scan()  # exercises Co{Initialize,Uninitialize}
    except Exception:
        pass  # COM errors propagate past finally; counts are set before re-raise

    assert counts["init"] == counts["uninit"], (
        f"CoInitialize/CoUninitialize unbalanced: init={counts['init']}, "
        f"uninit={counts['uninit']}"
    )


def test_scan_skips_uninit_when_init_failed(monkeypatch):
    """If pythoncom can't be imported, CoUninitialize must NOT run."""
    counts = {"uninit": 0}
    fake_pythoncom = types.ModuleType("pythoncom")
    fake_pythoncom.CoUninitialize = lambda: counts.__setitem__("uninit", counts["uninit"] + 1)

    sys.modules.pop("pythoncom", None)
    class _Blocker:
        def find_module(self, name, path=None):
            if name == "pythoncom":
                return self
            return None
        def load_module(self, name):
            raise ImportError("blocked for test")
    blocker = _Blocker()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])

    import flowdrip_app as fa
    mon = fa.OutlookMonitor()
    mon._scan()

    assert counts["uninit"] == 0, "Uninit must not run when init failed"
