with open('contract/templates/contract/detail.html', 'r') as f:
    content = f.read()

old_wrapper = '<div class="overflow-x-auto">'
new_wrapper = '<div class="overflow-x-auto scroll-fade" style="content-visibility: auto; contain-intrinsic-size: 500px;">'

content = content.replace(old_wrapper, new_wrapper)

with open('contract/templates/contract/detail.html', 'w') as f:
    f.write(content)
print("Success")
