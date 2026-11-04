# -*- coding: utf-8 -*-
import re, os

# Parse REGISTRY keys
with open('strategies/_registry.py', 'r') as f:
    content = f.read()

# Extract REGISTRY keys
reg_match = re.search(r"REGISTRY\s*=\s*\{(.*?)\n_MODULE_CACHE", content, re.DOTALL)
reg_block = reg_match.group(1)
registry_keys = re.findall(r"'([^']+)'(?:\s*dict|\s*,)", reg_block)

# Extract ENABLED_BATCH tuple
batch_match = re.search(r"ENABLED_BATCH\s*=\s*\((.*?)\)", content, re.DOTALL)
batch_block = batch_match.group(1)
enabled_keys = re.findall(r"'([^']+)'", batch_block)

# Get .py files in strategies/
py_files = set()
for f in os.listdir('strategies'):
    if f.endswith('.py') and not f.startswith('_'):
        py_files.add(f[:-3])

reg_set = set(registry_keys)
enabled_set = set(enabled_keys)

not_enabled = sorted(reg_set - enabled_set)
extra_enabled = sorted(enabled_set - reg_set)
files_not_in_reg = sorted(py_files - reg_set)
files_in_reg = sorted(py_files & reg_set)

out = []
out.append("REGISTRY total: " + str(len(reg_set)))
out.append("ENABLED_BATCH total: " + str(len(enabled_keys)))
out.append("VALID enabled (in REGISTRY): " + str(len(enabled_set & reg_set)))
out.append("Extra in ENABLED but not in REGISTRY: " + str(extra_enabled))
out.append("")
out.append("Strategies in REGISTRY but NOT in ENABLED_BATCH: " + str(len(not_enabled)))
for k in not_enabled:
    out.append("  - " + k)
out.append("")
out.append("Strategy .py files NOT in REGISTRY: " + str(len(files_not_in_reg)))
for f in files_not_in_reg:
    out.append("  - " + f + ".py")
out.append("")
out.append("Strategy .py files IN REGISTRY: " + str(len(files_in_reg)))
missing_py = sorted(reg_set - py_files)
if missing_py:
    out.append("Missing .py files for registry entries: " + str(missing_py))
else:
    out.append("All registry entries have corresponding .py files")

with open("registry_analysis_output.txt", "w") as f:
    f.write("\n".join(out))
print("Output written to registry_analysis_output.txt")
