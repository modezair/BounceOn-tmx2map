import sys
import xml.etree.ElementTree as ET
import base64
import struct

BO_OBJECT_IDS = {
    'start':        0x00,
    'walker':       0x01,
    'hatwalker':    0x01,
    'maskwalker':   0x01,
    'jumper':       0x02,
    'roller':       0x03,
    'worm':         0x04,
    'stalactite':   0x05,
    'spikey':       0x06,
    'slimey':       0x07,
    'wiffle':       0x08,
    'metal':        0x09,
    'magnet':       0x0A,
    'bubble':       0x0B,
    'speed':        0x0C,
    'fireball':     0x0D,
    'level':        0x0F,
    'cannon':       0x10,
    'checkpoint':   0x11,
    'sign':         0x12,
    'exit':         0x13,
    'life':         0x14,
    'door':         0x15,
    'seesaw':       0x16,
    'brokenlight':  0x17,
    'shockey':      0x18,
    'arrow':        0x1A,
    'evileyes':     0x1C,
    'water':        0x1D,
    'spike':        0x20,
    'barrier':      0x21,
    'secret':       0x22,
    'fall':         0x27,
    'block':        0x28,
    'spider':       0x29,
    'trap':         0x2A,
    'shooter':      0x2B,
    'snowman':      0x2D,
    'ice':          0x31,
}

BO_LEVEL_DIFFICULTIES = {
    'easy': 1,
    'medium': 2,
    'hard': 3,
    'veryhard': 4,
    'very hard': 4,
}

class BOObject:
    x:int
    y:int
    objtype:int
    arg1:int
    arg2:int
    arg3:int
    realx1:int
    realy1:int
    realx2:int
    realy2:int
    extended:str
    def __init__(self, lvlheight:int, tag:ET.Element):
        objwidth = tag.attrib.get('width')
        objheight = tag.attrib.get('height')
        self.realx1 = int(tag.attrib['x'])
        self.realy2 = (lvlheight << 5) - int(tag.attrib['y']) + (0 if objheight else 32)
        self.realx2 = self.realx1 + (int(objwidth) if objwidth else 32)
        self.realy1 = self.realy2 - (int(objheight) if objheight else 32)
        self.x = self.realx1 >> 5
        self.y = self.realy1 >> 5
        self.arg1 = 0
        self.arg2 = 0
        self.arg3 = 0
        self.extended = ""
        if 'name' not in tag.attrib:
            self.objtype = -1
            print(f"warning: ignored object with blank name of id {tag.attrib['id'] if 'id' in tag.attrib else "unknown"}")
            return
        name = tag.attrib['name'].lower().strip()
        if name not in BO_OBJECT_IDS:
            self.objtype = -1
            print(f"warning: ignored unknown object name \'{name}\' of id {tag.attrib['id']}")
            return
        else:
            self.objtype = BO_OBJECT_IDS[name]
        match name:
            case 'hatwalker':
                self.arg1 = 3
            case 'maskwalker':
                self.arg1 = 4

            case 'level':
                self.arg1 = BO_LEVEL_DIFFICULTIES.get(tag.attrib.get('type', 'easy'), 1)
                props = tag.find("properties")
                if props is None:
                    return
                proplevel = props.find("property")
                if proplevel is None:
                    return
                if proplevel.attrib['name'] != 'level':
                    return
                self.extended = proplevel.attrib['value']

            case 'sign':
                props = tag.find("properties")
                if props is None:
                    return
                proptext = props.find("property")
                if proptext is None:
                    return
                if proptext.attrib['name'] != 'text':
                    return
                self.extended = proptext.attrib['value']

            case 'arrow':
                props = tag.find("properties")
                if props is None:
                    return
                propangle = props.find("property")
                if propangle is None:
                    return
                if propangle.attrib['name'] != 'angle':
                    return
                self.arg1 = int(propangle.attrib['value'])

            case 'shooter':
                props = tag.find("properties")
                if props is None:
                    self.arg1 = 1000
                    return
                propdelay = props.find("property")
                if propdelay is None:
                    self.arg1 = 1000
                    return
                if propdelay.attrib['name'] != 'delay':
                    self.arg1 = 1000
                    return
                self.arg1 = int(propdelay.attrib['value'])

class BOMap:
    width:int
    height:int
    bgdata:list[bytes]
    colldata:list[bytes]
    fgdata:list[bytes]
    objs:list[BOObject]

    def __init__(self):
        self.width = 0
        self.height = 0
        self.bgdata = []
        self.colldata = []
        self.fgdata = []
        self.objs = []

def bo_layerdata(layername:str, layers:list[ET.Element]):
    result = []
    for layer in layers:
        ldatasrc = layer.find('data')
        if ldatasrc is not None:
            if ldatasrc.attrib.get('encoding') != 'base64' or ldatasrc.attrib.get('compression') != 'gzip':
                raise Exception(f"Invalid {layername} layer {layer.attrib.get('name')}. All layers must be stored using Tile Layer Format = Base64 (gzip compressed)")

            ldata = ldatasrc.text
            if ldata:
                result.append(base64.b64decode(ldata))

    return result

def main(infname:str, outfname:str, argv:dict):
    f = ET.parse(infname)
    root = f.getroot()
    if root.tag != 'map':
        raise Exception("Invalid TMX file")
    
    # The map must be fixed and have tile size 32x32
    hdr = root.attrib
    if hdr['infinite'] == '1':
        raise Exception("Infinite TMX files are not supported. Please use a fixed-size TMX file.")
    if hdr['tilewidth'] != '32' or hdr['tileheight'] != '32':
        raise Exception("Tile size must be 32x32")

    result = BOMap()
    result.width = int(hdr['width'])
    result.height = int(hdr['height'])

    # Look for the background, collision and foreground folders
    foundbg = False
    foundcl = False
    foundfg = False
    layersbg = []
    layerscl = []
    layersfg = []
    for g in root.findall('group'):
        if g.attrib['name'] == 'background':
            layersbg = g.findall('layer')
            foundbg = True
        elif g.attrib['name'] == 'collision':
            layerscl = g.findall('layer')
            foundcl = True
        elif g.attrib['name'] == 'foreground':
            layersfg = g.findall('layer')
            foundfg = True

    if not foundcl:
        raise Exception("Collision group not found")
    
    # Extract the layer data
    result.bgdata = bo_layerdata('background', layersbg)
    result.colldata = bo_layerdata('collision', layerscl)
    if len(result.colldata) == 0:
        raise Exception("It is mandatory to have at least one collision layer")
    result.fgdata = bo_layerdata('foreground', layersfg)

    # Read the objects
    xmlobjs = root.find('objectgroup')
    if xmlobjs is not None:
        for i in xmlobjs.findall('object'):
            result.objs.append(BOObject(result.height, i))

    # Read complete!
    # Now write the MAP file

    fo = open(outfname, "wb")
    fo.write(struct.pack(
        "<IIIIII",
        result.width,
        result.height,
        0, # I don't know what this value means yet
        len(result.bgdata),
        len(result.colldata) - 1,
        len(result.fgdata)
    ))

    # Write the layers

    for i in result.bgdata:
        fo.write(struct.pack("<I", len(i)))
        fo.write(i)
    for i in result.colldata:
        fo.write(struct.pack("<I", len(i)))
        fo.write(i)
    for i in result.fgdata:
        fo.write(struct.pack("<I", len(i)))
        fo.write(i)

    # Count the no. of known object types
    numobjs = 0
    for i in result.objs:
        if i.objtype == -1:
            continue
        numobjs += 1

    # Write objects
    fo.write(struct.pack("<I", numobjs))
    for i in result.objs:
        # Skip unknown objects
        if i.objtype == -1:
            continue
        fo.write(struct.pack("<iiiiiiiiiii",
                             i.x,
                             i.y,
                             i.objtype,
                             i.arg1,
                             i.arg2,
                             i.arg3,
                             i.realx1,
                             i.realy1,
                             i.realx2,
                             i.realy2,
                             len(i.extended)
                             ))
        if len(i.extended) > 0:
            fo.write(i.extended.encode())

    # Platforms & parallax backgrounds are not currently supported.
    # Write counters of 0 for both.
    fo.write(b'\0\0\0\0\0\0\0\0')

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(f"Usage: python {sys.argv[0]} <input.tmx> [-o<output.map>]")
    else:
        # Argument parsing
        argv = {}
        for i in sys.argv[1:]:
            if i.startswith('-'):
                if i[1] == '-':
                    argdata = i[2:].split('=', 1)
                    argv[argdata[0]] = argdata[1] if len(argdata) == 2 else None
                else:
                    argv[i[1]] = i[2:]
        
        main(
            sys.argv[1],
            argv['o'] if 'o' in argv.keys()
                else (sys.argv[1].rsplit('.', 1)[0] + ".map"),
            {}
        )
