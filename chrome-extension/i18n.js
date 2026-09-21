(() => {
  const locales=['en','ko','zh','ja'];
  // Columns: English, Korean, Simplified Chinese, Japanese.
  const rows={
    language:['Language','언어','语言','言語'],autoLanguage:['Automatic (browser)','자동 (브라우저 언어)','自动（浏览器语言）','自動（ブラウザーの言語）'],
    sending:['Sending to NASDrop…','NASDrop으로 보내는 중…','正在发送到 NASDrop…','NASDropへ送信中…'],
    success:['Added to NASDrop.','NASDrop에 추가했습니다.','已添加到 NASDrop。','NASDropに追加しました。'],
    login:['Open the extension and sign in to NASDrop first.','확장 아이콘을 눌러 NASDrop에 먼저 로그인하세요.','请先打开扩展并登录 NASDrop。','拡張機能を開いてNASDropにログインしてください。'],
    failed:['Could not send. Check your connection.','전송하지 못했습니다. 연결 상태를 확인하세요.','发送失败，请检查连接。','送信できませんでした。接続を確認してください。'],
    uncertain:['Result unknown. Check NASDrop jobs before retrying.','전송 결과를 확인하지 못했습니다. 재시도 전에 NASDrop 작업 목록을 확인하세요.','无法确认结果。重试前请检查 NASDrop 任务列表。','結果を確認できません。再試行前にNASDropのジョブを確認してください。'],
    resolving:['Resolving the Buzzheavier download link…','Buzzheavier 다운로드 링크 확인 중…','正在获取 Buzzheavier 下载链接…','Buzzheavierのダウンロードリンクを確認中…'],
    expiredLink:['Download link expired. Refresh the page and try again.','다운로드 링크가 만료됐습니다. 페이지를 새로고침한 후 다시 시도하세요.','下载链接已过期，请刷新页面后重试。','リンクの期限が切れました。ページを再読み込みしてください。'],
    serverUnsupported:['This NASDrop server does not support browser handoff for this site yet.','연결된 NASDrop 서버가 이 사이트의 브라우저 전송을 아직 지원하지 않습니다.','此 NASDrop 服务尚不支持该网站的浏览器传输。','このNASDropサーバーはこのサイトからの転送にまだ対応していません。'],
    close:['Close','닫기','关闭','閉じる'],passwordTitle:['NASDrop · Archive password required','NASDrop · 압축 비밀번호 필요','NASDrop · 需要压缩密码','NASDrop · アーカイブのパスワードが必要'],
    passwordMessage:['Open the extension and select this job to enter its password.','확장을 열고 이 작업을 눌러 비밀번호를 입력하세요.','打开扩展并选择此任务以输入密码。','拡張機能でこのジョブを選び、パスワードを入力してください。'],
    addedMany:['{count} files added','파일 {count}개 추가됨','已添加 {count} 个文件','{count}件を追加しました'],
    menuLink:['Send link to NASDrop','링크를 NASDrop으로 보내기','发送链接到 NASDrop','リンクをNASDropへ送信'],menuPage:['Send page to NASDrop','페이지를 NASDrop으로 보내기','发送页面到 NASDrop','ページをNASDropへ送信'],
    requestFailed:['Request failed.','요청에 실패했습니다.','请求失败。','リクエストに失敗しました。'],
    invalidJobs:['Invalid job list received.','올바르지 않은 작업 목록을 받았습니다.','收到无效的任务列表。','無効なジョブ一覧を受信しました。'],
    invalidAddress:['NASDrop address must use HTTP or HTTPS.','NASDrop 주소는 HTTP 또는 HTTPS여야 합니다.','NASDrop 地址必须使用 HTTP 或 HTTPS。','NASDropのアドレスにはHTTPまたはHTTPSを使用してください。'],
    embeddedCredentials:['Enter a server address without embedded credentials.','아이디나 비밀번호가 포함되지 않은 서버 주소를 입력하세요.','请输入不含用户名或密码的服务器地址。','認証情報を含まないサーバーアドレスを入力してください。'],
    enterAddress:['Open the NASDrop extension and enter your server address.','NASDrop 확장을 열고 서버 주소를 입력하세요.','打开 NASDrop 扩展并输入服务器地址。','NASDrop拡張機能でサーバーアドレスを入力してください。'],
    signIn:['Sign in to NASDrop first.','NASDrop에 먼저 로그인하세요.','请先登录 NASDrop。','先にNASDropにログインしてください。'],
    unreachable:['Could not reach the NASDrop server. Check its address and network connection.','NASDrop 서버에 연결할 수 없습니다. 주소와 네트워크를 확인하세요.','无法连接 NASDrop 服务，请检查地址和网络。','NASDropサーバーに接続できません。アドレスとネットワークを確認してください。'],
    invalidLink:['Enter a valid HTTP or HTTPS download link.','올바른 HTTP 또는 HTTPS 다운로드 링크를 입력하세요.','请输入有效的 HTTP 或 HTTPS 下载链接。','有効なHTTPまたはHTTPSのダウンロードリンクを入力してください。'],
    invalidJob:['Invalid job ID.','올바르지 않은 작업 ID입니다.','任务 ID 无效。','無効なジョブIDです。'],
    invalidOption:['Invalid extraction option.','올바르지 않은 압축 해제 설정입니다.','解压选项无效。','無効な展開設定です。'],
    invalidLanguage:['Invalid language.','지원하지 않는 언어입니다.','不支持此语言。','対応していない言語です。'],
    invalidRequest:['Invalid download request.','올바르지 않은 다운로드 요청입니다.','下载请求无效。','無効なダウンロードリクエストです。'],
    noBuzzLink:['Buzzheavier did not provide a download link. Refresh the page and try again.','Buzzheavier가 다운로드 링크를 제공하지 않았습니다. 페이지를 새로고침하고 다시 시도하세요.','Buzzheavier 未提供下载链接，请刷新页面后重试。','Buzzheavierからリンクを取得できません。ページを再読み込みしてください。'],
    httpError:['NASDrop request failed ({status}).','NASDrop 요청 실패 ({status}).','NASDrop 请求失败（{status}）。','NASDropリクエストに失敗しました（{status}）。'],
    inspecting:['Inspecting','확인 중','检查中','確認中'],queued:['Queued','대기 중','排队中','待機中'],ready:['Ready','준비 완료','已就绪','準備完了'],downloading:['Downloading','다운로드 중','下载中','ダウンロード中'],waiting_processing:['Waiting for processing','후처리 대기','等待处理','処理待ち'],verifying:['Verifying','검증 중','验证中','検証中'],extracting:['Extracting','압축 해제 중','解压中','展開中'],publishing:['Saving output','파일 저장 중','保存文件中','ファイル保存中'],stopping:['Stopping','중지 중','正在停止','停止処理中'],paused:['Paused','일시정지','已暂停','一時停止'],password_required:['Password required','비밀번호 필요','需要密码','パスワードが必要'],completed:['Completed','완료','已完成','完了'],failedStatus:['Failed','실패','失败','失敗'],cancelled:['Cancelled','취소됨','已取消','キャンセル済み'],
  };
  const dictionaries=Object.fromEntries(locales.map((locale,index)=>[locale,Object.fromEntries(Object.entries(rows).map(([key,values])=>[key,values[index]]))]));
  const normalize=value=>{const code=String(value||'en').toLowerCase().split(/[-_]/)[0];return locales.includes(code)?code:'en';};
  const resolve=(saved,browser)=>saved&&saved!=='auto'?normalize(saved):normalize(browser);
  const t=(locale,key,vars={})=>Object.entries(vars).reduce((text,[name,value])=>text.split(`{${name}}`).join(String(value)),dictionaries[normalize(locale)][key]||dictionaries.en[key]||key);
  const errors=Object.fromEntries(['uncertain','serverUnsupported','requestFailed','invalidJobs','invalidAddress','embeddedCredentials','enterAddress','signIn','unreachable','invalidLink','invalidJob','invalidOption','invalidLanguage','invalidRequest','noBuzzLink'].map(key=>[rows[key][0],key]));
  const error=(locale,message)=>{
    if(errors[message])return t(locale,errors[message]);
    const match=/^NASDrop request failed \((\d+)\)\.$/.exec(message||'');
    return match?t(locale,'httpError',{status:match[1]}):message||t(locale,'requestFailed');
  };
  globalThis.NASDropI18n={locales,dictionaries,normalize,resolve,t,error};
})();
