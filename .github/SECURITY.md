# Security Policy

## Supported Versions

| Version | Support Status |
|---------|---------------|
| 2.4.x   | Full security updates |
| 2.3.x   | Critical vulnerabilities only |
| < 2.3   | No longer supported |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

### How to Report

1. **Use GitHub's Private Security Reporting**
   - Go to [Security Advisories](https://github.com/PoppaShell/WarPie/security/advisories/new)
   - Click "Report a vulnerability"
   - Complete the vulnerability report form

### What to Include

- **Description**: Clear summary of the vulnerability
- **Affected Component**: Which part of WarPie (e.g., `warpie-control.py`, `wardrive.sh`)
- **Reproduction Steps**: Detailed steps to reproduce the issue
- **Impact Assessment**: Severity and potential consequences
- **Suggested Fix** (optional): If you have a proposed solution

### Response Timeline

| Action | Timeline |
|--------|----------|
| Initial acknowledgment | Within 48 hours |
| Vulnerability assessment | Within 1 week |
| Security patch release | Within 4 weeks (Critical/High) |

## Out of Scope

The following are NOT considered security vulnerabilities:

- **Theoretical attacks** without practical exploit demonstration
- **Social engineering** attacks targeting users
- **Physical access** attacks (WarPie assumes physical security)
- **Third-party dependencies** (report to respective projects: Kismet, gpsd, etc.)
- **Intended functionality** for security research when used as documented

## Security Considerations

### Web Control Panel (Port 1337)
- Runs with elevated privileges for service management
- No authentication by default (assumes trusted network)
- Should not be exposed to untrusted networks

### WiFi Capture
- Requires monitor mode on WiFi adapters
- Captured data may contain sensitive information
- Use exclusion filters for sensitive networks

### GPS and Location Data
- Logs contain precise location information
- Protect log files from unauthorized access

## Security Best Practices

- Change the default AP password from `wardriving`
- Restrict access to port 1337 to trusted devices
- Protect `/etc/warpie/` configuration files
- Secure Kismet logs in `~/kismet/logs/`
- Be aware of local laws regarding WiFi packet capture

---

**Last Updated**: December 2025
