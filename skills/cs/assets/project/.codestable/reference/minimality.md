# Minimality and artifact admission

Before adding code or structure, answer in order:

1. Does the required behavior already exist?
2. Can the current call/data path or project pattern be reused?
3. Can deletion or simplification remove the failure mode?
4. Can the standard library or platform facility do it?
5. Can an already-installed dependency do it?
6. What is the smallest coherent change that produces discriminating evidence?

Before adding an artifact, identify its consumer:

- Agent retrieval;
- Harness/checker validation;
- runtime behavior;
- independent reviewer;
- durable human decision.

No consumer means session-local notes, not a repository file. Do not add an abstraction, dependency, compatibility path, configuration switch, role simulation or process document for hypothetical future use. Follow the real system and remove obsolete parallel paths once the canonical path is proven.
