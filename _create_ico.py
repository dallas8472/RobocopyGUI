from PIL import Image
import os
p='logo.png'
if not os.path.exists(p):
    print('logo.png not found')
else:
    img=Image.open(p).convert('RGBA')
    sizes=[256,128,64,48,32,16]
    img.save('RobocopyGUI.ico', sizes=[(s,s) for s in sizes])
    print('RobocopyGUI.ico created')
