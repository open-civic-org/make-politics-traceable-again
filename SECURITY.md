# Security Policy

## Reporting a vulnerability

Please report security issues privately. Do not open a public GitHub issue for vulnerabilities that could expose secrets, enable unauthorized admin access, or leak sensitive personal data.

Email or contact the maintainers via a private channel agreed by the project. Include:

- Description of the issue
- Steps to reproduce
- Potential impact
- Suggested fix if known

We aim to acknowledge reports within a few business days.

## Secrets

- Never commit `.env`, API keys, credentials, or private keys.
- Use `.env.example` for non-secret templates only.
- Rotate any credential that may have been exposed.

## Privacy

Avoid publishing residential addresses, phone numbers, personal email, Aadhaar, PAN, signatures, or unnecessary dependent information — even when present in public source documents. Expose only what is needed for legitimate public accountability.

## Admin access

Admin MFA, RBAC, and audit logging are required before any production admin portal. Do not expose admin endpoints without authentication.
