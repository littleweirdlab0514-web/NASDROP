(() => {
  const messages = {
    en: {
      language:"Language", loginHint:"Direct browser access and other devices require the NASDrop access code. Opening the DSM icon signs in automatically.", accessCode:"Access code", openDashboard:"Open dashboard",
      dashboard:"Dashboard", settings:"Settings", runningOnNas:"Running on NAS", downloads:"Downloads", linkLabel:"GigaFile, GoFile, or Pixeldrain download link", downloadNow:"Download to NAS",
      destination:"Destination", checking:"Checking…", checkingShort:"Checking", chooseFolder:"Choose folder", jobs:"Jobs", loading:"Loading…", clearCompleted:"Clear completed",
      selected:"{count} selected", selectAll:"Select all", clearSelection:"Clear selection", pause:"Pause", resume:"Resume", delete:"Delete",
      clientConnection:"Client connection", scanQr:"Scan the QR code to configure connection details automatically.", showCode:"Show code", hideCode:"Hide code", copy:"Copy", rotate:"Regenerate", preparingQr:"Preparing QR…",
      defaultFolder:"Default destination", defaultFolderHint:"Jobs are saved here unless another folder is selected.", change:"Change", parallelTitle:"Parallel downloads from the same service",
      parallelHint:"Off by default. When enabled, multiple jobs from services such as GoFile may start together.", allowParallel:"Allow parallel downloads", sameServiceMax:"Maximum per service",
      twoJobs:"2 jobs", threeJobs:"3 jobs", warning:"Warning", parallelWarning:"Each job can use up to 8 connections. Three active jobs may create up to 24 connections, increasing rate-limit risk and NAS CPU, disk, and network load.",
      off:"Off", saveParallel:"Save parallel-download settings", folderPermissions:"Folder permissions", folderPermissionsHint:"Locked shared folders are not accessible. In DSM Shared Folder permissions, grant read/write access to this package's internal system user.",
      serviceAccount:"Service account", serviceAddress:"Service address", serviceAddressHint:"Use this address and access code from DSM and connected clients.", accessMethodHint:"The DSM icon passes the access code automatically. Direct browser access and other devices must enter it.", version:"Version",
      sponsorTitle:"Support NASDrop", sponsorHint:"If NASDrop is useful to you, you can support its continued development on GitHub Sponsors.", sponsorAction:"Sponsor on GitHub",
      folderTitle:"Choose destination folder", close:"Close", up:"Up", cancel:"Cancel", chooseThisFolder:"Choose this folder", requestFailed:"The request could not be completed.",
      statusQueued:"Queued", statusReady:"Ready", statusDownloading:"Downloading", statusVerifying:"Verifying", statusPaused:"Paused", statusCompleted:"Completed", statusFailed:"Error", statusCancelled:"Stopped",
      writable:"Writable", permissionRequired:"Permission required", notSelected:"Not selected", packageWritable:"Package account can write", dedicatedAccount:"Dedicated package account",
      gofileCooldown:"GoFile protection pause · automatically resumes after {time}. Do not retry repeatedly.", sameServiceSummary:"Up to {count} from the same service", qrAlt:"NASDrop client connection QR", qrFailed:"Could not create QR: {error}",
      processing:"{count} processing", noQueuedJobs:"No queued jobs", noJobsTitle:"No download jobs.", noJobsHint:"Add a link to manage its progress here.", scheduled:"Scheduled", integrity:"File verification details",
      confirmDelete:"Delete the {count} selected job records?", inspectLink:"Checking the link…", addedMany:"Added {count} files to the {target} queue.", addedOne:"Added {name} to the {target} queue.",
      confirmClear:"Delete all {count} completed job records?", confirmParallel:"Run up to {count} jobs from the same service at once? Rate limiting and NAS load may increase.", saving:"Saving…",
      parallelSaved:"Up to {count} jobs from the same service can now run together.", sequentialSaved:"Jobs from the same service will run one at a time.", loadingFolders:"Loading folders…",
      currentWritable:"Files can be saved in this folder.", currentNotWritable:"This location cannot be selected. Choose a writable subfolder.", browse:"Browse", noSubfolders:"No subfolders to display.",
      defaultChanged:"Default destination changed to {target}.", copied:"Access code copied.", confirmRotate:"Regenerating the access code disconnects existing clients and browsers. Continue?", rotated:"A new access code was issued. Reconnect existing devices with the new QR code."
    },
    ko: {
      language:"언어", loginHint:"주소를 직접 열거나 다른 기기에서 접속하면 NASDrop 접근 코드가 필요합니다. DSM 아이콘으로 열면 자동 로그인됩니다.", accessCode:"접근 코드", openDashboard:"대시보드 열기",
      dashboard:"대시보드", settings:"설정", runningOnNas:"NAS에서 실행 중", downloads:"다운로드", linkLabel:"GigaFile, GoFile 또는 Pixeldrain 다운로드 링크", downloadNow:"NAS로 바로 다운로드",
      destination:"저장 위치", checking:"확인 중…", checkingShort:"검사 중", chooseFolder:"폴더 선택", jobs:"작업 목록", loading:"불러오는 중…", clearCompleted:"완료 항목 정리",
      selected:"{count}개 선택", selectAll:"전체 선택", clearSelection:"선택 해제", pause:"일시정지", resume:"재개", delete:"삭제",
      clientConnection:"클라이언트 연결", scanQr:"QR을 스캔하면 연결 정보가 자동으로 설정됩니다.", showCode:"코드 보기", hideCode:"코드 숨기기", copy:"복사", rotate:"재발급", preparingQr:"QR을 준비하는 중…",
      defaultFolder:"기본 저장 폴더", defaultFolderHint:"작업에서 폴더를 따로 고르지 않으면 이 위치에 저장합니다.", change:"변경", parallelTitle:"같은 서비스 동시 다운로드",
      parallelHint:"기본값은 꺼짐입니다. 켜면 GoFile 등 같은 서비스의 여러 작업을 함께 시작합니다.", allowParallel:"동시 다운로드 허용", sameServiceMax:"같은 서비스 최대",
      twoJobs:"2개", threeJobs:"3개", warning:"주의", parallelWarning:"작업 하나가 최대 8개 연결을 사용하므로 전체 3개 실행 시 최대 24개 연결이 생길 수 있습니다. 속도 제한·일시 차단 및 NAS CPU·디스크·네트워크 부하가 증가할 수 있습니다.",
      off:"꺼짐", saveParallel:"동시 다운로드 설정 저장", folderPermissions:"폴더 접근 권한", folderPermissionsHint:"권한이 없는 공유 폴더는 잠금 표시됩니다. DSM 공유 폴더 권한에서 이 패키지의 시스템 내부 사용자에게 읽기/쓰기를 허용하세요.",
      serviceAccount:"서비스 계정", serviceAddress:"서비스 주소", serviceAddressHint:"DSM과 연결된 클라이언트에서 이 주소와 접근 코드를 사용합니다.", accessMethodHint:"DSM 아이콘은 접근 코드를 자동으로 전달합니다. 주소를 직접 열거나 다른 기기에서 접속하면 코드를 입력해야 합니다.", version:"버전",
      sponsorTitle:"NASDrop 후원", sponsorHint:"NASDrop이 유용했다면 GitHub Sponsors에서 지속적인 개발을 후원할 수 있습니다.", sponsorAction:"GitHub에서 후원하기",
      folderTitle:"저장 폴더 선택", close:"닫기", up:"상위", cancel:"취소", chooseThisFolder:"이 폴더 선택", requestFailed:"요청을 처리하지 못했습니다.",
      statusQueued:"대기 중", statusReady:"준비", statusDownloading:"다운로드 중", statusVerifying:"검증 중", statusPaused:"일시정지", statusCompleted:"완료", statusFailed:"오류", statusCancelled:"중지됨",
      writable:"쓰기 가능", permissionRequired:"권한 필요", notSelected:"선택되지 않음", packageWritable:"패키지 계정 쓰기 가능", dedicatedAccount:"패키지 전용 계정",
      gofileCooldown:"GoFile 보호 대기 중 · {time} 이후 자동 해제됩니다. 반복 시도하지 마세요.", sameServiceSummary:"같은 서비스 최대 {count}개", qrAlt:"NASDrop 클라이언트 연결 QR", qrFailed:"QR 생성 실패: {error}",
      processing:"{count}개 처리 중", noQueuedJobs:"대기 중인 작업 없음", noJobsTitle:"다운로드 작업이 없습니다.", noJobsHint:"링크를 추가하면 이곳에서 진행 상태를 관리할 수 있습니다.", scheduled:"예약 대기", integrity:"파일 검증 정보",
      confirmDelete:"선택한 {count}개 작업 기록을 삭제할까요?", inspectLink:"링크를 확인하는 중…", addedMany:"{count}개 파일을 {target} 대기열에 추가했습니다.", addedOne:"{name} 파일을 {target} 대기열에 추가했습니다.",
      confirmClear:"완료된 {count}개 작업 기록을 모두 삭제할까요?", confirmParallel:"같은 서비스 작업을 최대 {count}개 동시에 실행할까요? 속도 제한·일시 차단 및 NAS 부하가 증가할 수 있습니다.", saving:"저장하는 중…",
      parallelSaved:"같은 서비스 동시 다운로드를 최대 {count}개로 설정했습니다.", sequentialSaved:"같은 서비스 작업은 한 번에 하나씩 실행합니다.", loadingFolders:"폴더를 불러오는 중…",
      currentWritable:"현재 폴더에 저장할 수 있습니다.", currentNotWritable:"현재 위치는 선택할 수 없습니다. 쓰기 가능한 하위 폴더를 선택하세요.", browse:"탐색", noSubfolders:"표시할 하위 폴더가 없습니다.",
      defaultChanged:"기본 저장 폴더를 {target}(으)로 변경했습니다.", copied:"접근 코드를 복사했습니다.", confirmRotate:"접근 코드를 재발급하면 기존 클라이언트와 브라우저의 연결이 모두 해제됩니다. 계속할까요?", rotated:"새 접근 코드를 발급했습니다. 기존 기기는 새 QR로 다시 연결해야 합니다."
    },
    ja: {
      language:"言語", loginHint:"アドレスを直接開く場合や別の端末から接続する場合は、NASDropのアクセスコードが必要です。DSMアイコンから開くと自動でログインします。", accessCode:"アクセスコード", openDashboard:"ダッシュボードを開く",
      dashboard:"ダッシュボード", settings:"設定", runningOnNas:"NASで実行中", downloads:"ダウンロード", linkLabel:"GigaFile、GoFile、またはPixeldrainのダウンロードリンク", downloadNow:"NASへダウンロード",
      destination:"保存先", checking:"確認中…", checkingShort:"確認中", chooseFolder:"フォルダーを選択", jobs:"ジョブ一覧", loading:"読み込み中…", clearCompleted:"完了項目を消去",
      selected:"{count}件選択", selectAll:"すべて選択", clearSelection:"選択解除", pause:"一時停止", resume:"再開", delete:"削除",
      clientConnection:"クライアント接続", scanQr:"QRコードを読み取ると接続情報が自動設定されます。", showCode:"コードを表示", hideCode:"コードを隠す", copy:"コピー", rotate:"再発行", preparingQr:"QRを準備中…",
      defaultFolder:"既定の保存先", defaultFolderHint:"別のフォルダーを選ばない場合、ここに保存します。", change:"変更", parallelTitle:"同一サービスの並列ダウンロード",
      parallelHint:"既定ではオフです。有効にするとGoFileなど同じサービスの複数ジョブを同時に開始します。", allowParallel:"並列ダウンロードを許可", sameServiceMax:"サービスごとの最大数",
      twoJobs:"2件", threeJobs:"3件", warning:"注意", parallelWarning:"1ジョブは最大8接続を使用します。3ジョブでは最大24接続となり、速度制限や一時ブロック、NASのCPU・ディスク・ネットワーク負荷が増える場合があります。",
      off:"オフ", saveParallel:"並列設定を保存", folderPermissions:"フォルダー権限", folderPermissionsHint:"アクセスできない共有フォルダーはロック表示されます。DSMの共有フォルダー権限で、このパッケージの内部システムユーザーに読み書きを許可してください。",
      serviceAccount:"サービスアカウント", serviceAddress:"サービスアドレス", serviceAddressHint:"DSMおよび接続済みクライアントで、このアドレスとアクセスコードを使用します。", accessMethodHint:"DSMアイコンはアクセスコードを自動的に渡します。アドレスを直接開く場合や別の端末ではコードを入力してください。", version:"バージョン",
      sponsorTitle:"NASDropを支援", sponsorHint:"NASDropがお役に立った場合は、GitHub Sponsorsで継続的な開発を支援できます。", sponsorAction:"GitHubで支援する",
      folderTitle:"保存先フォルダーを選択", close:"閉じる", up:"上へ", cancel:"キャンセル", chooseThisFolder:"このフォルダーを選択", requestFailed:"リクエストを処理できませんでした。",
      statusQueued:"待機中", statusReady:"準備完了", statusDownloading:"ダウンロード中", statusVerifying:"検証中", statusPaused:"一時停止", statusCompleted:"完了", statusFailed:"エラー", statusCancelled:"停止済み",
      writable:"書き込み可", permissionRequired:"権限が必要", notSelected:"未選択", packageWritable:"パッケージアカウントで書き込み可", dedicatedAccount:"パッケージ専用アカウント",
      gofileCooldown:"GoFile保護待機中 · {time}以降に自動再開します。繰り返し試行しないでください。", sameServiceSummary:"同一サービス最大{count}件", qrAlt:"NASDropクライアント接続QR", qrFailed:"QRを作成できません: {error}",
      processing:"{count}件処理中", noQueuedJobs:"待機中のジョブはありません", noJobsTitle:"ダウンロードジョブはありません。", noJobsHint:"リンクを追加すると、ここで進行状況を管理できます。", scheduled:"予約待機", integrity:"ファイル検証情報",
      confirmDelete:"選択した{count}件のジョブ履歴を削除しますか？", inspectLink:"リンクを確認中…", addedMany:"{count}ファイルを{target}のキューに追加しました。", addedOne:"{name}を{target}のキューに追加しました。",
      confirmClear:"完了した{count}件のジョブ履歴をすべて削除しますか？", confirmParallel:"同一サービスのジョブを最大{count}件同時実行しますか？速度制限やNAS負荷が増える場合があります。", saving:"保存中…",
      parallelSaved:"同一サービスのジョブを最大{count}件同時実行するよう設定しました。", sequentialSaved:"同一サービスのジョブは1件ずつ実行します。", loadingFolders:"フォルダーを読み込み中…",
      currentWritable:"このフォルダーに保存できます。", currentNotWritable:"この場所は選択できません。書き込み可能なサブフォルダーを選択してください。", browse:"開く", noSubfolders:"表示できるサブフォルダーはありません。",
      defaultChanged:"既定の保存先を{target}に変更しました。", copied:"アクセスコードをコピーしました。", confirmRotate:"アクセスコードを再発行すると既存のクライアントとブラウザーが切断されます。続行しますか？", rotated:"新しいアクセスコードを発行しました。既存の端末は新しいQRで再接続してください。"
    },
    zh: {
      language:"语言", loginHint:"直接打开地址或从其他设备连接时需要输入NASDrop访问代码。从DSM图标打开时会自动登录。", accessCode:"访问代码", openDashboard:"打开控制面板",
      dashboard:"控制面板", settings:"设置", runningOnNas:"正在NAS上运行", downloads:"下载", linkLabel:"GigaFile、GoFile或Pixeldrain下载链接", downloadNow:"下载到NAS",
      destination:"保存位置", checking:"正在检查…", checkingShort:"检查中", chooseFolder:"选择文件夹", jobs:"任务列表", loading:"正在加载…", clearCompleted:"清除已完成项",
      selected:"已选择{count}项", selectAll:"全选", clearSelection:"取消选择", pause:"暂停", resume:"继续", delete:"删除",
      clientConnection:"客户端连接", scanQr:"扫描二维码即可自动配置连接信息。", showCode:"显示代码", hideCode:"隐藏代码", copy:"复制", rotate:"重新生成", preparingQr:"正在生成二维码…",
      defaultFolder:"默认保存位置", defaultFolderHint:"未另选文件夹时，任务将保存到此位置。", change:"更改", parallelTitle:"同一服务并行下载",
      parallelHint:"默认关闭。启用后，可同时启动GoFile等同一服务的多个任务。", allowParallel:"允许并行下载", sameServiceMax:"每个服务的最大数量",
      twoJobs:"2项", threeJobs:"3项", warning:"注意", parallelWarning:"每个任务最多使用8个连接。3个活动任务最多会产生24个连接，可能增加限速、临时封禁以及NAS的CPU、磁盘和网络负载。",
      off:"关闭", saveParallel:"保存并行下载设置", folderPermissions:"文件夹权限", folderPermissionsHint:"无权访问的共享文件夹会显示为锁定。请在DSM共享文件夹权限中，向此套件的内部系统用户授予读写权限。",
      serviceAccount:"服务账户", serviceAddress:"服务地址", serviceAddressHint:"DSM和已连接客户端使用此地址和访问代码。", accessMethodHint:"DSM图标会自动传递访问代码。直接打开地址或从其他设备连接时必须输入该代码。", version:"版本",
      sponsorTitle:"支持NASDrop", sponsorHint:"如果NASDrop对您有帮助，可以通过GitHub Sponsors支持项目的持续开发。", sponsorAction:"在GitHub上支持",
      folderTitle:"选择保存文件夹", close:"关闭", up:"上一级", cancel:"取消", chooseThisFolder:"选择此文件夹", requestFailed:"无法完成请求。",
      statusQueued:"等待中", statusReady:"准备就绪", statusDownloading:"下载中", statusVerifying:"验证中", statusPaused:"已暂停", statusCompleted:"已完成", statusFailed:"错误", statusCancelled:"已停止",
      writable:"可写", permissionRequired:"需要权限", notSelected:"未选择", packageWritable:"套件账户可写", dedicatedAccount:"套件专用账户",
      gofileCooldown:"GoFile保护等待中 · 将在{time}后自动恢复。请勿反复重试。", sameServiceSummary:"同一服务最多{count}项", qrAlt:"NASDrop客户端连接二维码", qrFailed:"无法生成二维码：{error}",
      processing:"正在处理{count}项", noQueuedJobs:"没有等待中的任务", noJobsTitle:"没有下载任务。", noJobsHint:"添加链接后可在此管理进度。", scheduled:"计划等待", integrity:"文件验证信息",
      confirmDelete:"要删除所选的{count}条任务记录吗？", inspectLink:"正在检查链接…", addedMany:"已将{count}个文件添加到{target}队列。", addedOne:"已将{name}添加到{target}队列。",
      confirmClear:"要删除全部{count}条已完成任务记录吗？", confirmParallel:"要同时运行最多{count}个同一服务的任务吗？限速风险和NAS负载可能增加。", saving:"正在保存…",
      parallelSaved:"已设置同一服务最多并行运行{count}个任务。", sequentialSaved:"同一服务的任务将逐个运行。", loadingFolders:"正在加载文件夹…",
      currentWritable:"可以保存到当前文件夹。", currentNotWritable:"无法选择当前位置。请选择可写的子文件夹。", browse:"浏览", noSubfolders:"没有可显示的子文件夹。",
      defaultChanged:"默认保存位置已更改为{target}。", copied:"访问代码已复制。", confirmRotate:"重新生成访问代码会断开现有客户端和浏览器。是否继续？", rotated:"已生成新的访问代码。现有设备需要使用新二维码重新连接。"
    }
  };

  const supported = Object.keys(messages);
  function normalize(value) {
    const code = String(value || "").toLowerCase().split("-")[0];
    return supported.includes(code) ? code : "en";
  }
  function detect() {
    const saved = localStorage.getItem("nasdrop-language");
    if (saved && supported.includes(saved)) return saved;
    for (const value of navigator.languages || [navigator.language]) {
      const code = normalize(value);
      if (code !== "en" || String(value || "").toLowerCase().startsWith("en")) return code;
    }
    return "en";
  }
  let language = detect();
  function t(key, vars = {}) {
    let value = messages[language][key] ?? messages.en[key] ?? key;
    Object.entries(vars).forEach(([name, replacement]) => { value = value.replaceAll(`{${name}}`, String(replacement)); });
    return value;
  }
  function apply() {
    document.documentElement.lang = language === "zh" ? "zh-CN" : language;
    document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(node => { node.placeholder = t(node.dataset.i18nPlaceholder); });
    document.querySelectorAll("[data-i18n-aria-label]").forEach(node => { node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel)); });
    document.querySelectorAll("[data-language-select]").forEach(node => { node.value = language; });
  }
  function setLanguage(value) {
    language = normalize(value);
    localStorage.setItem("nasdrop-language", language);
    apply();
    window.dispatchEvent(new CustomEvent("nasdrop-language-change"));
  }
  window.NASDropI18n = { t, apply, setLanguage, get language() { return language; } };
  document.querySelectorAll("[data-language-select]").forEach(node => node.addEventListener("change", event => setLanguage(event.target.value)));
  apply();
})();
