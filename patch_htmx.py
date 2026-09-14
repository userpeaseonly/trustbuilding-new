with open('dashboard/templates/base.html', 'r') as f:
    content = f.read()

config_script = """    <script>
        document.addEventListener('DOMContentLoaded', function() {
            if (window.htmx) {
                htmx.config.globalViewTransitions = true;
            }
        });
    </script>
"""

content = content.replace("    <script src=\"{% static 'js/htmx-preload.min.js' %}\" defer></script>", "    <script src=\"{% static 'js/htmx-preload.min.js' %}\" defer></script>\n" + config_script)

with open('dashboard/templates/base.html', 'w') as f:
    f.write(content)
print("Success")
