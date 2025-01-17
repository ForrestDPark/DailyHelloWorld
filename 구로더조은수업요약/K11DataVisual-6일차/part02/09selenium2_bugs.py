# -*- coding: utf-8 -*-
import pandas as pd
from selenium import webdriver
from bs4 import BeautifulSoup

driver = webdriver.Chrome('./driver/chromedriver.exe')
url = 'https://music.bugs.co.kr/chart'
driver.get(url)

html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')

song_data = [] 
rank = 1 
songs = soup.select('table.byChart > tbody > tr') 
for song in songs: 
    title = song.select('p.title > a')[0].text 
    singer = song.select('p.artist > a')[0].text 
    print(title, singer, sep="|")
    song_data.append (['Bugs', rank, title, singer]) 
    rank = rank + 1
    
columns = ['서비스', '순위', '타이틀', '가수'] 
pd_data = pd.DataFrame(song_data, columns = columns) 
pd_data.to_excel('./save/bugs.xlsx', index=False)

