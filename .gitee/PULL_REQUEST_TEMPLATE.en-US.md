# Project/Module - PR Type
*Example: 【# BugCapsule - Bug Fix】 or 【# BugCapsule - New Feature】*

---

## 📝 Summary (One Sentence)
> This PR: ________________________  
> *Example: Fixes an intermittent login token refresh failure and adds a retry mechanism.*

---

## 📋 Basic Information
- **Related Issue**: `#issue-number` (If none, describe the source of the requirement or the issue background.)
- **PR Type**: `New Feature` / `Bug Fix` / `Performance Improvement` / `Refactoring` / `Documentation Update` / `Build/Dependency Change`

---

## 🎯 Purpose (Why)
> Describe in detail the problem this PR solves and the goal it aims to achieve. Include any background not covered in the summary.

---

## 🔧 Changes (What)
- List the main changes by module/file:
  - `path/file`: Adjusted the xxx logic; explain the reason and impact.
  - Call out any database, configuration, or API compatibility changes.
- **Breaking Change**: Yes / No (If yes, include a migration plan.)

---

## ✅ Testing and Verification (Quality Assurance)
- [ ] Unit tests: Added / Updated / Not Required (__ passed, __% coverage)
- [ ] Integration tests: Critical flows are covered (e.g., sign in → perform action → sign out)
- [ ] Manual test scenarios (normal / error / boundary):
  - Normal flow: ...
  - Error scenarios: timeouts, network errors, insufficient permissions, etc.
  - Boundary cases: empty data, high concurrency, etc.
- [ ] Regression impact: List potentially affected existing features and confirm there are no regressions

---

## 📎 Additional Information (Optional)
- External changes this PR depends on (e.g., third-party library upgrades or database migrations)
- TODOs / future improvements
- Screenshots, logs, or performance data

---

## 🧾 Pre-Submission Checklist (Check Each Item)
- [ ] The code passes lint checks and builds successfully
- [ ] Debug code has been removed; logs are clear and naming conventions are followed
- [ ] Documentation (README / API / deployment) has been updated where necessary
- [ ] No security risks have been introduced (secrets, injection vulnerabilities, XSS, etc.)
- [ ] The branch has been rebased onto the latest main branch with no conflicts
- [ ] The PR title follows the required format (e.g., `[FEAT]` / `[FIX]` / `[REFACTOR]`)
