const COPY_TEXT_CHANGE_OFFSET = 1000;
const COPY_BUTTON_TEXT_BEFORE = 'COPY';
const COPY_BUTTON_TEXT_AFTER = 'COPIED!';
const COPY_ERROR_MESSAGE = "ERROR";

const codeWrappers = document.querySelectorAll('pre[id^=code_]');

const copyBlockCode = async (target = null) => {
    if (!target) return;
    try {
      const code = decodeURI(target.dataset.code);
      // code copy 기능 비동기 동작 
      await navigator.clipboard.writeText(code);
      target.innerHTML = COPY_BUTTON_TEXT_AFTER;
      setTimeout(() => {
        target.innerHTML = COPY_BUTTON_TEXT_BEFORE;
      }, COPY_TEXT_CHANGE_OFFSET);
    } catch (error) {
      alert(COPY_ERROR_MESSAGE);
      console.error(error);
    }
};




const func = () => {
    const codeBlocks = document.querySelectorAll("pre > code");

    for (const codeBlock of codeBlocks) {
      const codes = codeBlock.innerHTML.match(/(.*)(\n|.*$)/g);

      // 마지막 라인 추가적으로 생성 방지
      const processedCodes = codes.reduce((prevCodes, curCode, counter) => {
        if (counter == codes.length - 1) {
          return prevCodes;
        } else {
          counter += 1;
          return prevCodes + `<div class="line">${curCode}</div>`;
        }
      }, "");

      const copyButton = `<button type="button" class="copy-btn" data-code="${encodeURI(codeBlock.textContent)}" onclick="copyBlockCode(this)">${COPY_BUTTON_TEXT_BEFORE}</button>`;

      const codeBody = `<div class="code-body">${processedCodes}</div>`;

      const codeHeader = `<div class="code-header"><span class="red mac_dot"></span><span class="yellow mac_dot"></span><span class="green mac_dot"></span>${copyButton}</div>`;

      codeBlock.innerHTML = codeHeader + codeBody;
    }

};

window.addEventListener("load", () => {
    func();
});