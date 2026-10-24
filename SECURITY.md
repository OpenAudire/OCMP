# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x     | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email your findings to [INSERT SECURITY EMAIL]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes

### What to Expect

- Acknowledgment within 48 hours
- Regular updates on our progress
- Credit in the security advisory (if desired)

### Scope

The following are in scope:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF vulnerabilities
- Information disclosure
- Remote code execution
- Privilege escalation

The following are out of scope:

- Denial of service attacks
- Social engineering
- Physical security
- Issues in dependencies (report to the upstream project)

## Security Measures

OCMP implements the following security measures:

### Authentication

- Argon2id password hashing
- Session-based authentication with secure cookies
- CSRF protection on all state-changing endpoints
- Rate limiting on authentication endpoints

### Data Protection

- Parameterized queries (SQL injection prevention)
- Input validation via Pydantic schemas
- Output encoding (XSS prevention)
- Secrets encrypted at rest

### AI Privacy

- No personal data sent to AI providers (enforced in code)
- Redaction of emails, phone numbers, IDs before AI calls
- Optional restriction to local AI providers only

### Infrastructure

- TLS everywhere (Caddy auto-HTTPS)
- Secure HTTP headers
- Dependency scanning (Dependabot, CodeQL)
- Regular security updates

## Security Checklist for Deployments

- [ ] Change all default passwords
- [ ] Set a strong `SECRET_KEY`
- [ ] Configure firewall rules
- [ ] Enable and configure backups
- [ ] Review AI provider settings
- [ ] Configure rate limiting
- [ ] Set up monitoring and alerting
