with open('dashboard/templates/base.html', 'r') as f:
    content = f.read()

# Replace old messages with Alpine dispatcher
old_messages_start = "{% if messages %}"
old_messages_end = "{% endif %}"

# Find block
start_idx = content.find(old_messages_start)
if start_idx != -1:
    end_idx = content.find(old_messages_end, start_idx) + len(old_messages_end)
    old_messages = content[start_idx:end_idx]
    
    new_messages = """{% include 'partials/toast_notifications.html' %}
{% if messages %}
<script>
    document.addEventListener('DOMContentLoaded', () => {
        {% for message in messages %}
            setTimeout(() => {
                window.dispatchEvent(new CustomEvent('notify', {
                    detail: {
                        type: '{{ message.tags|default:"info" }}',
                        message: '{{ message|escapejs }}'
                    }
                }));
            }, {{ forloop.counter0 }} * 100);
        {% endfor %}
    });
</script>
{% endif %}"""

    content = content.replace(old_messages, new_messages)

with open('dashboard/templates/base.html', 'w') as f:
    f.write(content)
print("Success")
