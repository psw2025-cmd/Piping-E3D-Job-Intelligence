# Agent instructions

## Company account maintenance

Read docs/COMPANY_LOGINS.md before working on company accounts. config/company_logins.csv is the shared account index. Passwords belong in the private credential store referenced by each row, never in tracked files, issues, logs or pull requests.

Before an authorized login, look up the company and exact domain. Use an existing account rather than creating a duplicate. After the user provides a new account or an authorized account creation/change succeeds, update the shared index and the private store together, preserving unrelated rows. Record verification_status accurately; user-supplied is not login-verified. Do not reuse one company's password for another.

Cloud agents must check whether the referenced private store is available. A CSV password_ref is a locator, not a password. If unavailable, request access through a private credential channel; do not claim to know or have tested the password. Having a saved account does not authorize password resets or application submission.

Follow SECURITY.md. Never commit private CSVs or decrypted passwords.
