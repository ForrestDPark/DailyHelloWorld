# -*- coding: utf-8 -*-
#셀레니움을 임포트 한다. 
from selenium import webdriver
#크롬 드라이버를 로드한다. 이때 웹브라우저가 실행된다. 
driver = webdriver.Chrome('./driver/chromedriver.exe')
#만약 실행되지 않는다면 라이브러리 설치와 드라이버 경로를 확인해본다. 

'''
셀레니움은 크롬 브라우저를 이용해서 크롤링할 페이지를 띄운후 데이터를 
가져온다. 이때 비동기통신(Ajax)을 통해 데이터를 로드하는 경우에는 
조금 늦게 로딩되는 경우가 있으므로 셀레니움에서는 '암묵적(암시적)대기'가
필요한 경우가 있다. 
아래는 암묵적으로 5초간 대기한다. 만약 로딩이 빨리된다면 즉시 크롤링을 
시작한다.  
'''
driver.implicitly_wait(5)

#아래와 같이 time모듈을 사용하는 경우에는 로딩과 상관없이 무조건 5초를
#대기한다. 반드시 필요한 경우에만 사용하도록 한다. 
# import time
# time.sleep(5)

#멜론 실시간 챠트 페이지로 접속하여 페이지정보(HTML소스)를 얻어온다.
url = 'https://www.melon.com/chart/index.htm'
driver.get(url)
html = driver.page_source

#뷰티플숩을 실행한다. html.parser를 로드한다. 
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, 'html.parser')

#파싱한 정보 저장을 위한 리스트를 생성한다. 
song_data = [] 
rank = 1
#셀렉터를 이용해서 반복되는 엘리먼트(챠트)를 얻어온다. 
songs = soup.select('tbody > tr') 
for song in songs: 
    #노래제목
    title = song.select('div.ellipsis.rank01 > span > a')[0].text 
    #가수
    singer = song.select('div.ellipsis.rank02 > a')[0].text 
    #좋아요 갯수
    favo = song.select('td:nth-child(8) > div > button > span.cnt')[0].text 
    
    #콘솔 출력시 |(파이프) 구분자를 사용한다. 
    print(title, singer, favo, sep="|")
    #파싱한 정보는 리스트에 저장한다. 
    song_data.append(['Melon', rank, title, singer, favo])
    rank += 1

#리스트에 저장된 내용을 데이터프레임으로 변환한다. 
import pandas as pd
#컬럼으로 사용할 리스트를 생성한다. 
columns = ['서비스','순위','타이틀','가수','좋아요'] 
#데이터프레임으로 변환시 컬럼을 추가한다. 
pd_data = pd.DataFrame(song_data, columns=columns)
#데이터프레임 상위 5개 행을 출력한다. 
print(pd_data.head())
#엑셀로 저장한다. 
pd_data.to_excel('./save/melon.xlsx', index=False)




