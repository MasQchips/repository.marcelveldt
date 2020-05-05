﻿# -*- coding: utf-8 -*-

import re

from platformcode import config, logger
from core.item import Item
from core import httptools, scrapertools, tmdb, servertools

host = 'https://cinemaclasic.atwebpages.com/'

perpage = 25 # preferiblemente un múltiplo de los elementos que salen en la web (5x10=50) para que la subpaginación interna no se descompense

def mainlist(item):
    return mainlist_pelis(item)

def mainlist_pelis(item):
    logger.info()
    itemlist = []

    itemlist.append(item.clone ( title = 'Últimas películas', action = 'list_all', url = host + 'pelicula/' ))

    itemlist.append(item.clone ( title = 'Por género', action = 'generos', search_type = 'movie' ))
    itemlist.append(item.clone ( title = 'Por año', action = 'anios', search_type = 'movie' ))

    itemlist.append(item.clone ( title = 'Por directores/directoras', action = 'directores_actores', tipo = 'directores' ))
    itemlist.append(item.clone ( title = 'Por actores/actrices', action = 'directores_actores', tipo = 'actores' ))

    itemlist.append(item.clone ( title = 'Buscar película ...', action = 'search', search_type = 'movie' ))

    return itemlist


def generos(item):
    logger.info()
    itemlist = []
    
    data = httptools.downloadpage(host).data
    
    bloque = scrapertools.find_single_match(data, '<ul id="menu-generos" class="menu">(.*?)</ul>')
    
    matches = scrapertools.find_multiple_matches(bloque, '<a href="([^"]+)"[^>]*>([^<]+)')
    for url, title in matches:
        itemlist.append(item.clone( action='list_all', title=title, url=url ))

    itemlist.append(item.clone( action = 'list_all', title = 'Animación', url = host + 'genero/animacion/' ))
    itemlist.append(item.clone( action = 'list_all', title = 'Ciencia ficción', url = host + 'genero/ciencia-ficcion/' ))
    itemlist.append(item.clone( action = 'list_all', title = 'Documental', url = host + 'genero/documental/' ))

    return sorted(itemlist, key=lambda it: it.title)

def anios(item):
    logger.info()
    itemlist = []
    
    data = httptools.downloadpage(host).data
    
    bloque = scrapertools.find_single_match(data, '<ul class="releases scrolling">(.*?)</ul>')
    
    matches = scrapertools.find_multiple_matches(bloque, '<a href="([^"]+)"[^>]*>([^<]+)</a>')
    for url, title in matches:
        itemlist.append(item.clone( action='list_all', title=title, url=url ))

    for ano in range(1967, 1914, -1):
        itemlist.append(item.clone( action = 'list_all', title = str(ano), url = host + 'ano/' + str(ano) + '/' ))

    return itemlist

def directores_actores(item):
    logger.info()
    itemlist = []
    
    data = httptools.downloadpage(host).data
    
    tipo = 'DIRIGIDAS POR' if item.tipo == 'directores' else 'ACTORES/ACTRICES'
    bloque = scrapertools.find_single_match(data, '<h2 class="widget-title">%s(.*?)</div>' % tipo)
    
    matches = scrapertools.find_multiple_matches(bloque, '<a href="([^"]+)"[^>]*>([^<]+)<span class="tag-link-count"> \((\d+)\)')
    for url, title, num in matches:
        itemlist.append(item.clone( action='list_all', title='%s (%s)' % (title, num), url=url ))

    return itemlist


def list_all(item): 
    logger.info()
    itemlist = []

    if not item.page: item.page = 0

    data = httptools.downloadpage(item.url).data
    if '<h1>Películas' in data: data = data.split('<h1>Películas')[1] # descartar lista de destacadas
    if '<div class="sidebar' in data: data = data.split('<div class="sidebar')[0] # descartar listas laterales
    # ~ logger.debug(data)

    matches = re.compile('<article(.*?)</article>', re.DOTALL).findall(data)
    num_matches = len(matches)

    for article in matches[item.page * perpage:]:
        url = scrapertools.find_single_match(article, ' href="([^"]+)"')
        title = scrapertools.find_single_match(article, '<h4>(.*?)</h4>')
        if not title: title = scrapertools.find_single_match(article, ' alt="([^"]+)"')
        if not url or not title: continue
        thumb = scrapertools.find_single_match(article, ' src="([^"]+)"')
        year = scrapertools.find_single_match(article, '<span>(\d{4})</span>')
        if not year: year = scrapertools.find_single_match(article, ' (\d{4})</span>')
        if not year: year = '-'
        plot = scrapertools.htmlclean(scrapertools.find_single_match(article, '<div class="texto">(.*?)</div>'))
        plot = re.sub('^Impactos: \d+', '', plot)
        
        title = title.replace('&#8211;', '-')
        if '-' in title: title = title.split('-')[0].strip() # Dos cabalgan juntos- John Ford
        if year and year in title: title = title.replace(year, '').strip() # The Doorway to Hell (La senda del crimen) 1930
        title_alt = title.split(' (')[0].strip() if ' (' in title else '' # para mejorar detección en tmdb

        itemlist.append(item.clone( action='findvideos', url=url, title=title, thumbnail=thumb, 
                                    contentType='movie', contentTitle=title, contentTitleAlt = title_alt, 
                                    infoLabels={'year': year, 'plot': plot} ))

        if len(itemlist) >= perpage: break

    tmdb.set_infoLabels(itemlist)

    # Subpaginación interna y/o paginación de la web
    buscar_next = True
    if num_matches > perpage: # subpaginación interna dentro de la página si hay demasiados items
        hasta = (item.page * perpage) + perpage
        if hasta < num_matches:
            itemlist.append(item.clone( title='>> Página siguiente', page=item.page + 1, action='list_all' ))
            buscar_next = False

    if buscar_next:
        next_page = scrapertools.find_single_match(data, '<a href="([^"]+)"[^>]*><span class="icon-chevron-right">')
        if next_page:
           itemlist.append(item.clone (url = next_page, page = 0, title = '>> Página siguiente', action = 'list_all'))

    return itemlist



def corregir_servidor(servidor):
    servidor = servertools.corregir_servidor(servidor)
    return servidor

def findvideos(item):
    logger.info()
    itemlist = []
    
    IDIOMAS = {'spanish':'Esp', 'vose':'VOSE'}

    data = httptools.downloadpage(item.url).data
    # ~ logger.debug(data)

    # Ver en línea
    for tipo in ['videos', 'download']:
        bloque = scrapertools.find_single_match(data, "<div id='%s'(.*?)</table>" % tipo)
        # ~ logger.debug(bloque)

        matches = scrapertools.find_multiple_matches(bloque, "<tr id='link-[^']+'>(.*?)</tr>")
        for enlace in matches:
            # ~ logger.debug(enlace)

            url = scrapertools.find_single_match(enlace, " href='([^']+)")
            if '.us.archive.org' in enlace: servidor = 'directo'
            elif 'archive.org' in enlace: servidor = 'archiveorg'
            else:
                servidor = corregir_servidor(scrapertools.find_single_match(enlace, "domain=([^'.]+)"))
            if not url or not servidor: continue
            tds = scrapertools.find_multiple_matches(enlace, '<td>(.*?)</td>')
            lang = tds[1].lower()
            other = 'hace ' + tds[3]
            # ~ other += ', ' + tipo
            
            itemlist.append(Item( channel = item.channel, action = 'play', server = servidor, 
                                  title = '', url = url,
                                  language = IDIOMAS.get(lang,lang), other = other
                           ))

    if len(itemlist) == 0:
        url = scrapertools.find_single_match(data, '<iframe.*?src="([^"]+)')
        if url:
            servidor = servertools.get_server_from_url(url)
            if servidor and servidor != 'directo': 
                url = servertools.normalize_url(servidor, url)
                itemlist.append(Item( channel = item.channel, action = 'play', server = servidor, 
                                      title = '', url = url
                               ))
        
    return itemlist

def play(item):
    logger.info()
    itemlist = []

    if host in item.url:
        data = httptools.downloadpage(item.url).data
        # ~ logger.debug(data)
        url = scrapertools.find_single_match(data, '<a id="link" rel="nofollow" href="([^"]+)')
        if url: 
            if 'ok.cinetux.me/player/ok/?v=' in url:
                data = httptools.downloadpage(url).data
                vid = scrapertools.find_single_match(data, ' src=".*?\#([^"]+)')
                if vid: 
                    itemlist.append(item.clone( server = 'okru', url='https://ok.ru/videoembed/' + vid ))
            else:
                itemlist.append(item.clone( url=servertools.normalize_url(item.server, url) ))
    else:
        itemlist.append(item.clone())

    return itemlist



def list_search(item):
    logger.info()
    itemlist = []

    if not item.page: item.page = 0

    data = httptools.downloadpage(item.url).data

    matches = re.compile('<div class="result-item">(.*?)</article>', re.DOTALL).findall(data)
    num_matches = len(matches)

    for article in matches[item.page * perpage:]:
        url = scrapertools.find_single_match(article, ' href="([^"]+)"')
        thumb = scrapertools.find_single_match(article, ' src="([^"]+)"')
        title = scrapertools.find_single_match(article, ' alt="([^"]+)"')
        if not url or not title: continue

        year = scrapertools.find_single_match(article, '<span class="year">(\d+)</span>')
        if not year: year = scrapertools.find_single_match(article, '<span>(\d{4})</span>')
        plot = scrapertools.htmlclean(scrapertools.find_single_match(article, '<p>(.*?)</p>'))
        plot = re.sub('^Impactos: \d+', '', plot)
        
        title = title.replace('&#8211;', '-')
        if '-' in title: title = title.split('-')[0].strip() # Dos cabalgan juntos- John Ford
        if year and year in title: title = title.replace(year, '').strip() # The Doorway to Hell (La senda del crimen) 1930
        title_alt = title.split(' (')[0].strip() if ' (' in title else '' # para mejorar detección en tmdb

        itemlist.append(item.clone( action='findvideos', url=url, title=title, thumbnail=thumb, 
                                    contentType='movie', contentTitle=title, contentTitleAlt = title_alt, 
                                    infoLabels={'year': year, 'plot': plot} ))

        if len(itemlist) >= perpage: break
            
    tmdb.set_infoLabels(itemlist)

    # Subpaginación interna y/o paginación de la web
    buscar_next = True
    if num_matches > perpage: # subpaginación interna dentro de la página si hay demasiados items
        hasta = (item.page * perpage) + perpage
        if hasta < num_matches:
            itemlist.append(item.clone( title='>> Página siguiente', page=item.page + 1, action='list_search' ))
            buscar_next = False

    if buscar_next:
        next_page = scrapertools.find_single_match(data, '<a href="([^"]+)"[^>]*><span class="icon-chevron-right">')
        if next_page:
           itemlist.append(item.clone (url = next_page, page = 0, title = '>> Página siguiente', action = 'list_search'))

    return itemlist

def search(item, texto):
    logger.info("texto: %s" % texto)
    try:
        item.url = host + '?s=' + texto.replace(" ", "+")
        return list_search(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error("%s" % line)
        return []
