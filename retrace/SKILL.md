---
name: retrace
description: Retrace obfuscated Android crash logs using a ProGuard/R8 mapping file
user-invocable: true
---


# ProGuard/R8 Retrace

Deobfuscate an Android crash log using a ProGuard/R8 mapping file and write a detailed analysis.

## Input
The user provides two file paths as arguments: `$ARGUMENTS`
- First argument: the ProGuard/R8 mapping file (e.g., `mapping.txt`)
- Second argument: the crash/ANR log file (e.g., `crash.txt`)

Both files are expected to be in the current working directory or provided as absolute paths.

## Instructions

1. **Read the crash log** to identify all obfuscated class names and methods. Look for patterns like:
   - `com.pspdfkit.internal.XX` (two-letter obfuscated class names)
   - `com.*.internal.*` short class names that look obfuscated
   - Method names like `.a(`, `.b(`, `.c(` with `SourceFile:` line references

2. **Search the mapping file** for each obfuscated class. The mapping format is:
   ```
   original.ClassName -> obfuscated.ClassName:
       original_line:original_line:return_type methodName(params):source_start:source_end -> obfuscated_method
   ```
   - To find a class: grep for `-> obfuscated.class.Name:` in the mapping file
   - To find methods: read the lines following the class mapping, match by obfuscated method name and line number

3. **Map obfuscated line numbers to source lines** using the mapping ranges:
   - `X:Y:returnType methodName(params):A:B -> obfuscatedName` means obfuscated lines X-Y map to source lines A-B
   - For a specific obfuscated line L within range X:Y, the source line = A + (L - X)

4. **Write output file** named `<crash-log-basename>-deobfuscated.txt` in the same directory as the crash log, containing:
   - The fully deobfuscated stack trace with original class names, method names, source files, and line numbers
   - A mapping table showing each obfuscated name -> original name
   - Analysis of the root cause including the full call chain reconstruction
   - Severity assessment and recommendations

5. **Analyze the crash/ANR**:
   - Reconstruct the full call chain with deobfuscated names
   - Identify the root cause (deadlock, mutex contention, exception, etc.)
   - Note which component/layer is responsible
   - Provide actionable recommendations
