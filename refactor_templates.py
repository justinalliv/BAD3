#!/usr/bin/env python3
import re
import os

def refactor_file(filepath):
    """Refactor a template file to extend base.html"""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract title
    title_match = re.search(r'<title>(.*?)</title>', content)
    title = title_match.group(1) if title_match else 'Supreme Biotech Solutions'
    
    # Extract style content
    style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
    styles = style_match.group(1) if style_match else ""
    
    # Extract body content
    body_match = re.search(r'<body>(.*?)</body>', content, re.DOTALL)
    body = body_match.group(1) if body_match else ""
    
    # Extract scripts
    script_matches = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
    scripts = '\n'.join(script_matches) if script_matches else ""
    
    # Remove nav from body
    body = re.sub(r'<!--.*?Navigation.*?-->.*?</nav>', '', body, flags=re.DOTALL)
    body = re.sub(r'<nav>.*?</nav>', '', body, flags=re.DOTALL)
    body = body.strip()
    
    # Clean styles - remove base/duplicate styles
    lines = styles.split('\n')
    cleaned_lines = []
    skip = False
    
    for line in lines:
        # Skip base styles
        if any(x in line for x in ['* {', 'body {', 'html {', 'nav {', '.nav-logo', 
                                    '.nav-links', '.profile-btn', '/* Navigation',
                                    '/* Responsive', '@media', '.btn {', '.btn-primary',
                                    'table {', 'thead', '.modal', '.status-badge']):
            skip = True
        elif skip and (line.strip() == '}' or ('{' not in line and '}' in line)):
            skip = False
            continue
        elif not skip and line.strip():
            cleaned_lines.append(line)
    
    clean_styles = '\n'.join(cleaned_lines).strip()
    
    # Build new template
    new_content = "{% extends 'base.html' %}\n\n"
    new_content += f"{{% block title %}}{title}{{% endblock %}}\n\n"
    
    if clean_styles:
        new_content += "{% block extra_css %}\n<style>\n"
        new_content += clean_styles + "\n"
        new_content += "</style>\n{% endblock %}\n\n"
    
    new_content += "{% block content %}\n"
    new_content += body + "\n"
    new_content += "{% endblock %}"
    
    if scripts.strip():
        new_content += "\n\n{% block extra_js %}\n<script>\n"
        new_content += scripts + "\n"
        new_content += "</script>\n{% endblock %}"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True

# Refactor remaining templates
os.chdir('/Users/justinateneo/Desktop/BAD3/SANG')

templates = [
    'sangapp/templates/service_status.html',
    'sangapp/templates/pending_payment.html',
    'sangapp/templates/payment_instructions.html',
    'sangapp/templates/submit_payment_proof.html',
]

for template in templates:
    try:
        refactor_file(template)
        print(f"✓ {template.split('/')[-1]}")
    except Exception as e:
        print(f"✗ {template.split('/')[-1]}: {str(e)}")

print("\nVerifying refactoring...")
for template in templates:
    with open(template, 'r') as f:
        first_line = f.readline().strip()
        if "extends 'base.html'" in first_line:
            print(f"✓ {template.split('/')[-1]} - extends base.html")
        else:
            print(f"✗ {template.split('/')[-1]} - NOT refactored properly")
