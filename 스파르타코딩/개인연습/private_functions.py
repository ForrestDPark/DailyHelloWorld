

class privateFunctions:
    
    
    def __init__(self) -> None:
        pass
    
    def openweather():
        # Web API application 
        import requests, json
        apiKey ="2f7291653dec89bb534b465e3669b92a"
        # 날씨를 확인할 도시 지정하기 
        cities = ['Seoul,KR', 'Tokyo,JP', "New York,US", "Beijing,CN"]
        # API 지정
        api = "http://api.openweathermap.org/data/2.5/weather?q={city}&APPID={key}"
        # 캘빈 온도 를 섭씨 온도로 변환 
        k2c = lambda k: f"{k-273.15:.2f}"
        # 각 도시의 정보 추출하기 
        for name in cities:
            url = api.format(city=name, key = apiKey)
            r = requests.get(url)
            data = json.loads(r.text) 
            # print(data)
            print(" + 도시=", data['name']) 
            print(" | 날씨 =", data['weather'][0]['description'])
            print(" | 최저기온 = ",k2c(data['main']['temp_min']))
            print(" | 최고기온 = ",k2c(data['main']['temp_max']))
            print(" | 습도 = ",(data['main']['humidity']))
            print(" | 기압 = ",(data['main']['pressure']))
            print(" | 풍향 = ",(data['wind']['deg']))
            print(" | 풍속  = ",(data['wind']['speed']))
    
    def printtest():
        print("test")
    
    def sqliteDB():
        import sqlite3
        # sqlite 데이터베이스 연결하기 
        dbPath = "../Data/test.sqlite"
        conn = sqlite3.connect(dbPath)
        #테이블을 생성하기 데이터 넣기 
        curs = conn.cursor()
        curs.executescript(
            """
            DROP TABLE IF EXISTS items;
            CREATE TABLE items(
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                price INTEGER
            );
            INSERT INTO items(name, price) VALUES ('Apple', 800);
            INSERT INTO items(name, price) VALUES ('Bnana', 800);
            INSERT INTO items(name, price) VALUES ('Orange', 800);
            """
        )
        # d위의 조작을 데이터베이스에 반영하기 
        # 데이터 추출하기 
        curs = conn.cursor()
        curs.execute("SELECT item_id, name, price FROM items")
        item_list = curs.fetchall()
        # item list 출력 
        for it in item_list:
            print(it)
        # connection 종료 
        conn.close()

    def multiInsertOnSqlite():
        import sqlite3
        # sqlite 데이터베이스 연결하기 
        dbPath = "../Data/test.sqlite"
        conn = sqlite3.connect(dbPath)
        #테이블을 생성하기 데이터 넣기 
        curs = conn.cursor()
        curs.executescript(
            """
            DROP TABLE IF EXISTS items;
            CREATE TABLE items(
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER
            );
            """
        )
        # 위의 조작을 데이터베이스에 반영하기 
        conn.commit()
        # 데이터 넣기 
        curs = conn.cursor()
        curs.execute("INSERT INTO items (name, price) VALUES (?,?)" , ("Orange",5200))
        conn.commit()
        # 여러 데이터 연속으로 넣기 
        curs = conn.cursor()
        data = [("Mango",7700),("Kiwi",4000)]
        curs.executemany("INSERT INTO items (name, price) VALUES (?,?)", data)
        conn.commit()
        # 데이터 추출
        curs = conn.cursor()
        curs.execute("SELECT item_id, name, price FROM items")
        item_list = curs.fetchall()

        # 
        for it in item_list:
            print(it)
        conn.close()
    
    def mySQLdatabase():
                print("test")
