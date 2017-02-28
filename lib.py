import xbmc

def log(msg, level=4):
    # TODO: REMOVE
    xbmc.log(msg=u'!!!!!!! BYTEFM:: ', level=level)
    xbmc.log(msg=unicode(msg).encode('utf-8', 'ignore'), level=level)
    xbmc.log(msg=u'!!!!!!! BYTEFM:: ', level=level)