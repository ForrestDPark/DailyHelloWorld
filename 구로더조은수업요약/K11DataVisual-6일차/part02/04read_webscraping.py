# -*- coding: utf-8 -*-
#읽어온 HTML소스에서 정보를 파싱한다. 
from bs4 import BeautifulSoup
#특정 URL로의 요청을 통해 페이지의 정보(HTML)을 읽어온다. 
import requests
#정보를 데이터프레임으로 변환 및 정규화 해준다. 
import pandas as pd

#크롤링할 URL을 준비한 후 request모듈을 통해 정보를 읽어온다. 
url = 'https://kin.naver.com/search/list.nhn?query=%ED%8C%8C%EC%9D%B4%EC%8D%AC'
response = requests.get(url)

#파싱한 정보를 저장하기위해 딕셔너리 객체를 생성한다. 
dicts = {}

#요청에 성공한 경우라면 파싱을 진행한다. 
if response.status_code==200:
    #얻어온 정보를 파싱하기 위해 soup객체로 변환한다. 
    html = response.text
    soup = BeautifulSoup(html, 'html.parser') 
    
    '''첫번째 제목을 가져와서 출력한다. 선택자는 개발자모드의 셀렉터
    복사 기능을 사용하면된다.'''
    title01 = soup.select_one('#s_content > div.section > ul > li:nth-child(1) > dl > dt')
    #print("첫번째제목(HTML코드포함):", title01)
    
    text01 = title01.get_text()
    #print("첫번째제목(텍스트만추출):", text01)
    
    '''ul태그 하위의 li태그가 반복되면서 검색된 내용을 출력하므로 
    엘리먼트를 얻어와 갯수만큼 반복한다. '''
    ul = soup.select_one('#s_content > div.section > ul')
    #print(ul)
    title02 = ul.select('li > dl > dt > a')
    #print(title02)
        
    cnt = 1
    for tit in title02:
        #print(tit.get_text())
        #크롤링한 순서대로 항목1~10까지 문자열을 생성한다. 
        '''Python에서는 문자열과 숫자를 연결할때 str() 함수를 통해
        숫자를 문자로 변환한 후 연결해야한다.'''
        my_key = '항목' + str(cnt) #str을 제거하면 에러발생됨
        '''파싱한 정보를 딕셔너리에 저장한다. key는 '항목N'을 사용하고
        value는 크롤링한 정보를 사용한다.'''
        dicts[my_key] = [tit.get_text(), '2행데이터']
        #'항목N'을 위해 cnt를 1증가시킨다. Python은 증감연산자가 없다.
        cnt += 1
    print(dicts)
else:
    #요청에 실패했다면 응답코드를 출력한다. 
    print(response.status_code)

#딕셔너리를 데이터프레임으로 변환한다. 
df = pd.DataFrame(dicts)
print("데이터 프레임 변환 후 출력")
print(df)






