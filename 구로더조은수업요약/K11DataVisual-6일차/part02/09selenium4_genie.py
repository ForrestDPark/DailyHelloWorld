# -*- coding: utf-8 -*-
#라이브러리 임포트
import pandas as pd
from selenium import webdriver
from bs4 import BeautifulSoup

#셀레니움 드라이버 로드 및 크롬 브라우저 열기
driver = webdriver.Chrome('./driver/chromedriver.exe')
url = 'https://www.genie.co.kr/chart/top200'
driver.get(url)

#페이지 정보를 얻어온후 숩 객체 생성
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')

#챠트의 1~50위까지의 데이터를 파싱한 후 리스트에 저장한다. 
song_data = [] 
rank = 1
#리스트(목록)는 대부분 table태그로 제작되므로 tr을 찾은후 반복하면된다. 
songs = soup.select('tbody > tr') 
for song in songs: 
    #제목과 가수를 가져온다. 
    title = song.select('a.title')[0].text.strip()
    singer = song.select('a.artist')[0].text 
    print(title, singer, sep="|")
    #정보를 리스트에 추가한다. 
    song_data.append(['Genie', rank, title, singer])
    rank += 1
#묵시적으로 2초간 대기한다. 
driver.implicitly_wait(2) 
#xpath를 통해 버튼을 찾은 후 클릭한다.  
driver.find_element_by_xpath(
    '//*[@id="body-content"]/div[7]/a[2]'
).click() 

#2페이지에 대한 정보를 새로 얻어온 후 크롤링을 시작한다. 
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')
songs = soup.select('tbody > tr') 
for song in songs: 
    title = song.select('a.title')[0].text.strip()
    singer = song.select('a.artist')[0].text 
    print(title, singer, sep="|")
    song_data.append(['Genie', rank, title, singer])
    rank += 1   
driver.implicitly_wait(2)  
driver.find_element_by_xpath(
    '//*[@id="body-content"]/div[7]/a[3]'
).click() 

#3페이지
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')
songs = soup.select('tbody > tr') 
for song in songs: 
    title = song.select('a.title')[0].text.strip()
    singer = song.select('a.artist')[0].text 
    print(title, singer, sep="|")
    song_data.append(['Genie', rank, title, singer])
    rank += 1
driver.implicitly_wait(2)  
driver.find_element_by_xpath(
    '//*[@id="body-content"]/div[7]/a[4]'
).click() 

#4페이지
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')
songs = soup.select('tbody > tr') 
for song in songs: 
    title = song.select('a.title')[0].text.strip()
    singer = song.select('a.artist')[0].text 
    print(title, singer, sep="|")
    song_data.append(['Genie', rank, title, singer])
    rank += 1
    
#데이터프레임에 컬럼을 추가한 후 변환한다. 
columns = ['서비스','순위','타이틀','가수'] 
pd_data = pd.DataFrame(song_data, columns=columns)
print(pd_data.head())
#엑셀로 저장한다. 
pd_data.to_excel('./save/genie.xlsx', index=False)

