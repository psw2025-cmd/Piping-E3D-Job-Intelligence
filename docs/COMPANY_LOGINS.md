# Company login register

The shared index is config/company_logins.csv. It records company, official login URL, user ID, private password reference, verification status and update date. It deliberately has no password column.

## Existing KBR account

The KBR password has been saved in a Windows DPAPI-encrypted private CSV on the user's local computer. It has not been tested against KBR. The value was preserved literally, including the supplied backslash.

Current private store location on that computer:

`C:\Users\ADMIN\Documents\Codex\2026-09-23\google-drive-plugin-google-drive-openai\outputs\company-logins\company_logins.private.csv`

The companion Get-CompanyCredential.ps1 returns a PSCredential for Company KBR. DPAPI decryption requires the same Windows user profile and machine. Do not print the decrypted password. This local store is not accessible automatically to GitHub or cloud agents.

## Add or update an account

1. Check the shared index for the same company, domain and user ID.
2. Save the user-authorized password in the private credential store. For the current Windows CSV, use ConvertFrom-SecureString without a custom key and preserve existing records.
3. Upsert the shared index with a reference such as private-store:COMPANY; never include the password itself.
4. Use user_supplied_not_tested until a successful authorized login is observed; then use login_verified and update the date.
5. Confirm the private store and index agree without logging passwords.

For cloud execution, provision the credentials separately through a supported secret store. Repository instructions and this index alone cannot provide password access. No GitHub secret has been configured by this change. Never copy the Windows encrypted CSV into GitHub; it is machine-bound and is not a cloud credential solution.

Local private files may be kept under the already ignored private-config/ directory. Keep Windows-specific encrypted stores on the machine where they were created.
