import shutil

p = r'D:\facefusion\venv\Lib\site-packages\gradio\templates\frontend\assets\Index-DI509U_e.js'
old = b'this.resize_ui_container.visible=!1),this.image_editor_context.background_image)'
new = b'this.resize_ui_container.visible=!1),this.image_editor_context&&this.image_editor_context.background_image)'

shutil.copyfile(p, p + '.bak')
data = open(p, 'rb').read()
print('occurrences before =', data.count(old))
data = data.replace(old, new)
open(p, 'wb').write(data)
print('occurrences after  =', open(p, 'rb').read().count(old))
print('guard present      =', open(p, 'rb').read().count(new))
