/* services/post-service.js */

// paginator util 객체를 생성 
const paginator = require("../utils/paginator")

const { ObjectId } = require("mongodb")

/* 1. 상세페이지 게시글 데이터를 가져오는 함수 */
const projectionOption = {
    projection: {
        // 프로젝션(투영) 결과값에서 일부만 가져올 떄 사용 
        password: 0,
        "comments.password":0,
    }
}
async function getDetailPost(collection, id) {
    // 몽고디비 Collection 의 findOneAndUpdate() 함수 사용 ()
    return await collection.findOneAndUpdate({ _id: new ObjectId(id)}, {$inc: { hits: 1}},projectionOption)
}

/* 2. post 목록 보여주는 함수 list*/
async function list(collection, page, search){
    const perPage = 10;
    // (1) title search 와 부분일치 하는지 확인 
    const query = {title: new RegExp(search, "i")}
    // (2) limit 은 10개 만 가져온다는의미 skip은 설정된 개수만큼 건너 뛴다(skip)
    // 생성일 역순으로 정렬 
    const cursor = collection
        .find(query, {limit : perPage, skip:(page-1) * perPage})
        .sort({createdDt: -1,})
    // (3) 검색어에 걸리는 게시물의 총합 
    const totalCount = await collection.count(query)
    // (4) 커서로 받아온 데이터를 리스트로 변경 
    const posts = await cursor.toArray() 
    console.log("[post-service.js >list()] 가져온 post 입니다 : ",posts)
    // (5) 페이지네이터 생성
    const paginatorObj = paginator({ totalCount, page, perPage: perPage })
    return [posts, paginatorObj]
}

/* 3. 글쓰기 함수  */
async function writePost(collection, post) {
    // 3.1 생성일시와 조회수를 입력 
    post.hits = 0
    // 3.2 날짜는 ISO 포맷으로 저장 
    post.createdDt = new Date().toISOString() 
    // 3.3 몽고 디비에 post 를 저장 후 결과 반환 
    return await collection.insertOne(post)

}


/* 4. post 의 id 와 password 로 수정 권한 확인하는 함수 */
async function getPostByIdAndPassword(collection, { id, password}) {
    // 4.1 findOne() 함수 사용 
    return await collection.findOne({ _id: new ObjectId(id), password: password},
projectionOption)
// _id : 문서 고유 식별 id ObjectId 라는 특수 형식으로 저장됨 
}
// 4.2 id 데이터 불러오기 
async function getPostById(collection, id ){
    return await collection.findOne({ _id: new ObjectId(id)}, projectionOption)
}
// 4.3 게시글 수정 될때 마다 update 를 해서 db 수정 한다. 
async function updatePost(collection, id, post){
    const toUpdatePost = {
        $set: {
            ...post,
        }
    }
    return await collection.updateOne({_id: new ObjectId(id)}, toUpdatePost)
}



/* 5. require() 로 파일을 임포트 시 외부로 노출하는 객체 */
module.exports ={
    writePost,list, getDetailPost,
    getPostById,
    getPostByIdAndPassword,
    updatePost
}