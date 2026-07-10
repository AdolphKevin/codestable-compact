# Minimality ladder

Before adding code or structure, answer in order:

1. Does the behavior already exist?
2. Can the existing code path or pattern be reused?
3. Can the standard library or platform-native facility do it?
4. Can an already-installed dependency do it?
5. Can deletion or simplification remove the root cause?
6. What is the smallest diff that proves acceptance?

Do not add an abstraction, dependency, artifact, compatibility layer or configuration option for hypothetical future use. Follow the actual call/data flow before editing. Prefer root-cause repair over symptom patches.
