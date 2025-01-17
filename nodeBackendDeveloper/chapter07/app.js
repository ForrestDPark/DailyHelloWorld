// app.js
/* 1. Libraries require  */
const express = require("express")
const handlebars = require("express-handlebars")
const app = express()
// 몽고 디비 연결 함수 
const mongodbConnection = require("./configs/mongodb-connection")
// 서비스 파일 로딩 
const postService = require("./services/post-service")

// 글 삭제시 필요한 db object id 객체 
const { ObjectId} = require("mongodb")


/* 2. 미들 웨어 설정 추가 req.body post 요청 해석 설정 */
app.use(express.json())
app.use(express.urlencoded({extended: true}))

/* 3.  app engine : 핸들바 커스텀 함수 설정 추가 */
app.engine(
    "handlebars", 
    handlebars.create({
        helpers: require("./configs/handlebars-helpers"),
    }).engine,
    handlebars.engine({ layoutsDir : "views"})
);

/* 4. view 템플릿 세팅 및 디렉터리 지정  Setting*/
app.set("view engine","handlebars") // 웹 페이지 로드시 사용할 템플릿 엔진 설정 
app.set("views", __dirname +"/views") // 뷰 디렉터리를 view 로 설정 

/*********ROUTE**********/
/* 1. root page */
app.get("/", async (req,res) => {
    // 1.1 현재 페이지 데이터 
    const page = parseInt(req.query.page) || 1;
    const search = req.query.search || "";
    try {
        // 1.2 postService.list 에서 글 목록과 페이지네이터를 가져옴 
        const [posts,paginator] = await postService.list(collection, page, search);
        // 1.3 list page 랜더링
        res.render("home", {
            title: " GRK partners project management",
            message: "GRK Partners!",
            search,
            paginator,
            posts
        })

    } catch (error) {
        console.log(error)
        // 1.4 error 가 나는 경우 빈값으로 렌더링 
        res.render("home", {
            title: " GRK partners project management",
            message: "GRK Partners!",
        })
    }
})

/* 2. write(글쓰기) */
app.get("/write", (req,res) => {
    res.render("write", {title : "Project board ", mode: "create"})
})

/* 6. 수정페이지로 이동  */
app.get("/modify/:id", async (req,res) => {
    const post = await postService.getPostById(collection, req.params.id)
    console.log(post)
    res.render("write", {title: "Project board", mode: "modify", post})
})
/* 7. 게시글 수정 api */
app.post("/modify/", async (req,res) => {
    const { id, title, writer, password, content} = req.body

    const post = {
        title,
        writer,
        password,
        content,
        createdDt : new Date().toISOString()
    }
    // 7.1 update 결과 
    const result = postService.updatePost(collection, id, post)
    res.redirect(`/detail/${id}`)

})


/* 3.  글쓰기 저장 post write */
app.post("/write", async (req, res) => {
    const post = req.body;
    // 3.1 글쓰기 후 결과 반환 
    const result = await postService.writePost(collection, post)
    // 3.2 생성된 document 의 _id 를 사용해 상세 페이지로 redirect 이동
    res.redirect(`/detail/${result.insertedId}`)
})

/* 4.detail page 상세 페이지로 이동 */
app.get("/detail/:id", async (req,res) => {

    // 4.1 게시글 정보 가져오기 
    try { 
        const post = await postService.getDetailPost(collection, req.params.id)
        console.log("data check : ",post)
        res.render("detail", {
            title: "게시글 상세 ",
            post : post
        })
    } catch (error) {
        console.error("상세 글 조회 중 에러 ",error)
        res.status(500).send('Error')
    }

    
})
/* 5. 글 수정 패스워드 체크  */
app.post("/check-password", async (req,res) => {
    const {id, password} = req.body
    // 5.1 postService 의 getPostByIdAndPassword() 함수를 사용해 게시글 데이터 확인 
    const post = await postService.getPostByIdAndPassword(collection, { id , password})
    if (!post) {
        return res.status(404).json({isExit : false})
    } else {
        return res.json({ isExit : true})
    }
})

/*8. 글 삭제  */
app.delete("/delete", async (req,res) =>{
    const {id, password} = req.body 
    try {
        // 8.1 collection deleteOne 을 사용해 게시글 하나 삭제 
        const result =await collection.deleteOne({ _id : new ObjectId(id), password: password})
        // 8.2 삭제 결과가 잘못된 경우 처리 
        if (result.deletedCount !== 1) {
            console.log("삭제 실패");
            return res.json({isSuccess: false})
        }
        return res.json({isSuccess: true})
    } catch (error) {
        console.error(error)
        return res.json({isSuccess:false})
    }

})
/* 9. 댓글 추가 API */
app.post("/write-comment", async (req,res) => {
    const {id, name, password, comment} = req.body
    const post = await postService.getPostById(collection, id)

    // 9.1 기존에 댓글들(post.comments) 있다면 push 로 comment 추가. 
    if (post.comments) {
        post.comments.push({
            idx: post.comments.length +1,
            name,
            password,
            comment,
            createdDt: new Date().toISOString()
        })
    } else {
        //9.2 댓글들이 없다면 comment 정보 추가 
        post.comments =[
            {
                idx : 1,
                name,
                password,
                comment,
                createdDt: new Date().toISOString()
            }
        ]
    }
    // 9.3 업데이트하기. 업데이트 후에는 상세페이지로 다시 리다이렉트 
    postService.updatePost(collection, id, post)
})



// app listen port & mongodb
let collection ;
app.listen(80, async () =>{
    console.log("Server started")
    // (1) mongodbConnection() 의 결과 mongoClient
    const mongoClient = await mongodbConnection()
    console.log(" Mongo client connection ")
    // (2) mongoClient.db() 로 db 선택 collection() 으로 컬랙션 선택후 collection에 할당.
    collection = mongoClient.db('board').collection("post")
    console.log(" board, post collection fetched  ")

    // try {
    //     await collection.insertOne({title : 'TestPost', content:' this is a test post'})
    //     console.log("test data inserted")
    // } catch (error) {
    //     console.error("Error inserting test data:", error)
    // }
})