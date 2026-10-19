import sys
sys.path.insert(0, r"C:\Users\UseR\AppData\Roaming\MetaQuotes\Terminal\FA97EA291D4188820508F9D2B5AAD50F\MQL5\Files\PythonProjects\StrategyCloud")

try:
    import py_compile
    py_compile.compile(r"dashboard.py", doraise=True)
    print("✅ dashboard.py — синтаксис OK")
except py_compile.PyCompileError as e:
    print(f"❌ Ошибка синтаксиса: {e}")
