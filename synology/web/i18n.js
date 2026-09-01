(() => {
  const messages = {
    en: {
      language:"Language", loginHint:"Sign in with the NASDrop ID and password configured on this NAS. Opening the DSM icon signs in automatically.", username:"ID", password:"Password", openDashboard:"Open dashboard", accountNotConfigured:"No account is configured. Open NASDrop from its DSM icon and create an ID and password first.", logout:"Sign out",
      dashboard:"Dashboard", settings:"Settings", runningOnNas:"Running on NAS", downloads:"Downloads", linkLabel:"GigaFile, GoFile, or Pixeldrain download link", downloadNow:"Download to NAS",
      destination:"Destination", checking:"Checking…", checkingShort:"Checking", chooseFolder:"Choose folder", jobs:"Jobs", loading:"Loading…", clearCompleted:"Clear completed",
      selected:"{count} selected", selectAll:"Select all", clearSelection:"Clear selection", pause:"Pause", resume:"Resume", delete:"Delete",
      clientConnection:"Client connection", accountHint:"Direct browsers and client apps sign in with this ID and password. The DSM icon continues to sign in automatically.", currentPassword:"Current password", newPassword:"New password", confirmPassword:"Confirm new password", passwordRules:"Use 10–128 characters. Passwords are stored only as a salted hash.", saveAccount:"Save ID and password", resetAccount:"Reset", resetAccountHint:"Enter a new ID and password, then save them. Existing client sessions will be signed out.", passwordMismatch:"The new passwords do not match.", accountSaved:"The client login ID and password were saved.",
      defaultFolder:"Default destination", defaultFolderHint:"Jobs are saved here unless another folder is selected.", change:"Change", parallelTitle:"Parallel downloads from the same service",
      parallelHint:"Off by default. When enabled, multiple jobs from services such as GoFile may start together.", allowParallel:"Allow parallel downloads", sameServiceMax:"Maximum per service",
      twoJobs:"2 jobs", threeJobs:"3 jobs", warning:"Warning", parallelWarning:"In 8-part mode, each job can use up to 8 connections. Three active jobs may create up to 24 connections, increasing rate-limit risk and NAS CPU, disk, and network load.",
      off:"Off", saveParallel:"Save parallel-download settings", folderPermissions:"Folder permissions", folderPermissionsHint:"Locked shared folders are not accessible. In DSM Shared Folder permissions, grant read/write access to this package's internal system user.",
      serviceAccount:"Service account", serviceAddress:"Service address", serviceAddressHint:"Use this address with the configured ID and password from connected clients.", accessMethodHint:"The DSM icon signs in automatically. Direct browser access and client apps must enter the ID and password.", version:"Version",
      launcherPort:"DSM icon external port", launcherPortHint:"Used when the DSM icon is opened through a public hostname. LAN access continues to use port 8791.", saveLauncherPort:"Save icon port", launcherPortSaved:"The DSM icon will use external port {port}.",
      downloadMethod:"Per-file download method", downloadMethodHint:"Single connection avoids splitting and merging while keeping the shared integrity checks.", method:"Method", segmentedMode:"8-part download + verification", singleMode:"Single connection + verification",
      singleModeWarningTitle:"Single-connection trade-off", singleModeWarning:"One connection lowers provider request pressure. The completed file is still size-checked and hashed, so disk reading continues during verification.", saveDownloadMethod:"Save download method", singleModeShort:"Single connection", segmentedModeShort:"8 parts + verification",
      sponsorTitle:"Support NASDrop", sponsorHint:"If NASDrop is useful to you, you can support its continued development on GitHub Sponsors.", sponsorAction:"Sponsor on GitHub",
      folderTitle:"Choose destination folder", close:"Close", up:"Up", cancel:"Cancel", chooseThisFolder:"Choose this folder", requestFailed:"The request could not be completed.",
      statusQueued:"Queued", statusReady:"Ready", statusDownloading:"Downloading", statusWaitingProcessing:"Waiting for disk processing", statusVerifying:"Verifying", statusExtracting:"Extracting", statusPublishing:"Moving to destination", statusPasswordRequired:"Password required", statusPaused:"Paused", statusCompleted:"Completed", statusFailed:"Error", statusCancelled:"Stopped",
      writable:"Writable", permissionRequired:"Permission required", notSelected:"Not selected", packageWritable:"Package account can write", dedicatedAccount:"Dedicated package account",
      gofileCooldown:"GoFile protection pause · automatically resumes after {time}. Do not retry repeatedly.", sameServiceSummary:"Up to {count} from the same service", qrAlt:"NASDrop client connection QR", qrFailed:"Could not create QR: {error}",
      processing:"{count} processing", noQueuedJobs:"No queued jobs", noJobsTitle:"No download jobs.", noJobsHint:"Add a link to manage its progress here.", scheduled:"Scheduled", integrity:"File verification details",
      confirmDelete:"Delete the {count} selected job records?", inspectLink:"Checking the link…", addedMany:"Added {count} files to the {target} queue.", addedOne:"Added {name} to the {target} queue.",
      confirmClear:"Delete all {count} completed job records?", confirmParallel:"Run up to {count} jobs from the same service at once? Rate limiting and NAS load may increase.", saving:"Saving…",
      parallelSaved:"Up to {count} jobs from the same service can now run together.", sequentialSaved:"Jobs from the same service will run one at a time.", loadingFolders:"Loading folders…",
      confirmSingleMode:"Use single-connection downloads? Provider request pressure is reduced while final integrity verification remains enabled.", singleModeSaved:"New and resumed jobs will use one connection and final integrity verification.", segmentedModeSaved:"New and resumed jobs will use 8 parts and full verification.",
      currentWritable:"Files can be saved in this folder.", currentNotWritable:"This location cannot be selected. Choose a writable subfolder.", browse:"Browse", noSubfolders:"No subfolders to display.",
      processingTitle:"Temporary workspace and extraction", processingHint:"Parts are downloaded and combined in a hidden workspace. Only completed results appear in the destination.", temporaryFolder:"Temporary folder", archiveEngine:"Archive engine", engineReady:"7-Zip ready", engineMissing:"Engine missing", autoExtract:"Use extraction by default for new jobs", diskProtection:"Pause new downloads during disk processing", archiveFormats:"ZIP, AES ZIP, 7z, RAR, and TAR-family archives are extracted into a folder named after the archive.", saveProcessing:"Save processing settings", autoExtractOn:"Default extraction on", autoExtractOff:"Default extraction off", processingSavedOn:"New jobs will default to extraction; each job can override it.", processingSavedOff:"New jobs will default to keeping archive files.", archiveExtracted:"Archive extracted · original archive kept only in the temporary workspace", extractThisJob:"Extract archives after download", archivePasswordOptional:"Archive password (optional)", archivePassword:"Archive password", retryExtraction:"Retry extraction",
      defaultChanged:"Default destination changed to {target}."
    },
    ko: {
      language:"언어", loginHint:"이 NAS에 설정한 NASDrop ID와 비밀번호로 로그인하세요. DSM 아이콘으로 열면 자동 로그인됩니다.", username:"ID", password:"비밀번호", openDashboard:"대시보드 열기", accountNotConfigured:"아직 계정이 설정되지 않았습니다. DSM 아이콘으로 NASDrop을 열어 ID와 비밀번호를 먼저 만드세요.", logout:"로그아웃",
      dashboard:"대시보드", settings:"설정", runningOnNas:"NAS에서 실행 중", downloads:"다운로드", linkLabel:"GigaFile, GoFile 또는 Pixeldrain 다운로드 링크", downloadNow:"NAS로 바로 다운로드",
      destination:"저장 위치", checking:"확인 중…", checkingShort:"검사 중", chooseFolder:"폴더 선택", jobs:"작업 목록", loading:"불러오는 중…", clearCompleted:"완료 항목 정리",
      selected:"{count}개 선택", selectAll:"전체 선택", clearSelection:"선택 해제", pause:"일시정지", resume:"재개", delete:"삭제",
      clientConnection:"클라이언트 연결", accountHint:"주소를 직접 연 브라우저와 클라이언트 앱은 이 ID와 비밀번호로 로그인합니다. DSM 아이콘은 계속 자동 로그인됩니다.", currentPassword:"현재 비밀번호", newPassword:"새 비밀번호", confirmPassword:"새 비밀번호 확인", passwordRules:"10~128자를 사용하세요. 비밀번호 원문은 저장하지 않고 솔트를 적용한 해시만 저장합니다.", saveAccount:"ID와 비밀번호 저장", resetAccount:"재설정", resetAccountHint:"새 ID와 비밀번호를 입력한 뒤 저장하세요. 기존 클라이언트는 모두 로그아웃됩니다.", passwordMismatch:"새 비밀번호가 서로 일치하지 않습니다.", accountSaved:"클라이언트 로그인 ID와 비밀번호를 저장했습니다.",
      defaultFolder:"기본 저장 폴더", defaultFolderHint:"작업에서 폴더를 따로 고르지 않으면 이 위치에 저장합니다.", change:"변경", parallelTitle:"같은 서비스 동시 다운로드",
      parallelHint:"기본값은 꺼짐입니다. 켜면 GoFile 등 같은 서비스의 여러 작업을 함께 시작합니다.", allowParallel:"동시 다운로드 허용", sameServiceMax:"같은 서비스 최대",
      twoJobs:"2개", threeJobs:"3개", warning:"주의", parallelWarning:"8분할 방식에서는 작업 하나가 최대 8개 연결을 사용하므로 전체 3개 실행 시 최대 24개 연결이 생길 수 있습니다. 속도 제한·일시 차단 및 NAS CPU·디스크·네트워크 부하가 증가할 수 있습니다.",
      off:"꺼짐", saveParallel:"동시 다운로드 설정 저장", folderPermissions:"폴더 접근 권한", folderPermissionsHint:"권한이 없는 공유 폴더는 잠금 표시됩니다. DSM 공유 폴더 권한에서 이 패키지의 시스템 내부 사용자에게 읽기/쓰기를 허용하세요.",
      serviceAccount:"서비스 계정", serviceAddress:"서비스 주소", serviceAddressHint:"연결된 클라이언트에서 이 주소와 설정한 ID·비밀번호를 사용합니다.", accessMethodHint:"DSM 아이콘은 자동 로그인됩니다. 주소를 직접 연 브라우저와 클라이언트 앱은 ID와 비밀번호를 입력해야 합니다.", version:"버전",
      launcherPort:"DSM 아이콘 외부 포트", launcherPortHint:"공개 호스트 이름으로 DSM 아이콘을 열 때 사용합니다. 내부망 접속은 계속 8791 포트를 사용합니다.", saveLauncherPort:"아이콘 포트 저장", launcherPortSaved:"DSM 아이콘이 외부 포트 {port}을(를) 사용합니다.",
      downloadMethod:"파일별 다운로드 방식", downloadMethodHint:"단일 연결은 분할·병합을 생략하면서 공통 무결성 검사는 유지합니다.", method:"방식", segmentedMode:"8분할 다운로드 + 검증", singleMode:"단일 연결 + 검증",
      singleModeWarningTitle:"단일 연결 사용 시 주의", singleModeWarning:"한 개 연결로 서비스 요청 부담을 줄입니다. 완료 파일의 크기와 해시는 계속 검사하므로 검증 중 디스크 읽기는 발생합니다.", saveDownloadMethod:"다운로드 방식 저장", singleModeShort:"단일 연결", segmentedModeShort:"8분할 + 검증",
      sponsorTitle:"NASDrop 후원", sponsorHint:"NASDrop이 유용했다면 GitHub Sponsors에서 지속적인 개발을 후원할 수 있습니다.", sponsorAction:"GitHub에서 후원하기",
      folderTitle:"저장 폴더 선택", close:"닫기", up:"상위", cancel:"취소", chooseThisFolder:"이 폴더 선택", requestFailed:"요청을 처리하지 못했습니다.",
      statusQueued:"대기 중", statusReady:"준비", statusDownloading:"다운로드 중", statusWaitingProcessing:"디스크 작업 대기", statusVerifying:"검증 중", statusExtracting:"압축 해제 중", statusPublishing:"최종 폴더로 이동 중", statusPasswordRequired:"암호 입력 필요", statusPaused:"일시정지", statusCompleted:"완료", statusFailed:"오류", statusCancelled:"중지됨",
      writable:"쓰기 가능", permissionRequired:"권한 필요", notSelected:"선택되지 않음", packageWritable:"패키지 계정 쓰기 가능", dedicatedAccount:"패키지 전용 계정",
      gofileCooldown:"GoFile 보호 대기 중 · {time} 이후 자동 해제됩니다. 반복 시도하지 마세요.", sameServiceSummary:"같은 서비스 최대 {count}개", qrAlt:"NASDrop 클라이언트 연결 QR", qrFailed:"QR 생성 실패: {error}",
      processing:"{count}개 처리 중", noQueuedJobs:"대기 중인 작업 없음", noJobsTitle:"다운로드 작업이 없습니다.", noJobsHint:"링크를 추가하면 이곳에서 진행 상태를 관리할 수 있습니다.", scheduled:"예약 대기", integrity:"파일 검증 정보",
      confirmDelete:"선택한 {count}개 작업 기록을 삭제할까요?", inspectLink:"링크를 확인하는 중…", addedMany:"{count}개 파일을 {target} 대기열에 추가했습니다.", addedOne:"{name} 파일을 {target} 대기열에 추가했습니다.",
      confirmClear:"완료된 {count}개 작업 기록을 모두 삭제할까요?", confirmParallel:"같은 서비스 작업을 최대 {count}개 동시에 실행할까요? 속도 제한·일시 차단 및 NAS 부하가 증가할 수 있습니다.", saving:"저장하는 중…",
      parallelSaved:"같은 서비스 동시 다운로드를 최대 {count}개로 설정했습니다.", sequentialSaved:"같은 서비스 작업은 한 번에 하나씩 실행합니다.", loadingFolders:"폴더를 불러오는 중…",
      confirmSingleMode:"단일 연결 다운로드를 사용할까요? 서비스 요청 부담은 줄이고 최종 무결성 검사는 유지합니다.", singleModeSaved:"새 작업과 재개 작업은 단일 연결과 최종 무결성 검사를 사용합니다.", segmentedModeSaved:"새 작업과 재개 작업은 8분할 다운로드와 전체 검증을 사용합니다.",
      currentWritable:"현재 폴더에 저장할 수 있습니다.", currentNotWritable:"현재 위치는 선택할 수 없습니다. 쓰기 가능한 하위 폴더를 선택하세요.", browse:"탐색", noSubfolders:"표시할 하위 폴더가 없습니다.",
      processingTitle:"임시 폴더 및 압축 해제", processingHint:"파일 조각은 숨김 임시 폴더에서 다운로드·결합되며 완성된 결과만 저장 폴더에 나타납니다.", temporaryFolder:"임시 폴더", archiveEngine:"압축 해제 엔진", engineReady:"7-Zip 준비됨", engineMissing:"엔진 없음", autoExtract:"새 작업의 압축 해제 기본값", diskProtection:"디스크 처리 중 새 다운로드 일시 정지", archiveFormats:"ZIP·AES ZIP·7z·RAR·TAR 계열 압축을 압축파일명과 같은 폴더로 안전하게 해제합니다.", saveProcessing:"처리 설정 저장", autoExtractOn:"기본 압축 해제 켜짐", autoExtractOff:"기본 압축 해제 꺼짐", processingSavedOn:"새 작업은 압축 해제가 기본이며 작업마다 변경할 수 있습니다.", processingSavedOff:"새 작업은 압축파일 보존이 기본입니다.", archiveExtracted:"압축 해제 완료 · 원본 압축 파일은 임시 공간에서만 사용됨", extractThisJob:"다운로드 후 압축 해제", archivePasswordOptional:"압축 암호(선택 사항)", archivePassword:"압축 암호", retryExtraction:"압축 해제 재시도",
      defaultChanged:"기본 저장 폴더를 {target}(으)로 변경했습니다."
    },
    ja: {
      language:"言語", loginHint:"このNASで設定したNASDropのIDとパスワードでログインしてください。DSMアイコンから開くと自動でログインします。", username:"ID", password:"パスワード", openDashboard:"ダッシュボードを開く", accountNotConfigured:"アカウントがまだ設定されていません。DSMアイコンからNASDropを開き、IDとパスワードを作成してください。", logout:"ログアウト",
      dashboard:"ダッシュボード", settings:"設定", runningOnNas:"NASで実行中", downloads:"ダウンロード", linkLabel:"GigaFile、GoFile、またはPixeldrainのダウンロードリンク", downloadNow:"NASへダウンロード",
      destination:"保存先", checking:"確認中…", checkingShort:"確認中", chooseFolder:"フォルダーを選択", jobs:"ジョブ一覧", loading:"読み込み中…", clearCompleted:"完了項目を消去",
      selected:"{count}件選択", selectAll:"すべて選択", clearSelection:"選択解除", pause:"一時停止", resume:"再開", delete:"削除",
      clientConnection:"クライアント接続", accountHint:"直接開いたブラウザーとクライアントアプリは、このIDとパスワードでログインします。DSMアイコンは引き続き自動ログインします。", currentPassword:"現在のパスワード", newPassword:"新しいパスワード", confirmPassword:"新しいパスワードの確認", passwordRules:"10～128文字を使用してください。パスワードの原文は保存せず、ソルト付きハッシュのみ保存します。", saveAccount:"IDとパスワードを保存", resetAccount:"再設定", resetAccountHint:"新しいIDとパスワードを入力して保存してください。既存のクライアントセッションはすべてログアウトされます。", passwordMismatch:"新しいパスワードが一致しません。", accountSaved:"クライアントログイン用のIDとパスワードを保存しました。",
      defaultFolder:"既定の保存先", defaultFolderHint:"別のフォルダーを選ばない場合、ここに保存します。", change:"変更", parallelTitle:"同一サービスの並列ダウンロード",
      parallelHint:"既定ではオフです。有効にするとGoFileなど同じサービスの複数ジョブを同時に開始します。", allowParallel:"並列ダウンロードを許可", sameServiceMax:"サービスごとの最大数",
      twoJobs:"2件", threeJobs:"3件", warning:"注意", parallelWarning:"8分割方式では1ジョブが最大8接続を使用します。3ジョブでは最大24接続となり、速度制限や一時ブロック、NASのCPU・ディスク・ネットワーク負荷が増える場合があります。",
      off:"オフ", saveParallel:"並列設定を保存", folderPermissions:"フォルダー権限", folderPermissionsHint:"アクセスできない共有フォルダーはロック表示されます。DSMの共有フォルダー権限で、このパッケージの内部システムユーザーに読み書きを許可してください。",
      serviceAccount:"サービスアカウント", serviceAddress:"サービスアドレス", serviceAddressHint:"接続するクライアントでは、このアドレスと設定したID・パスワードを使用します。", accessMethodHint:"DSMアイコンは自動ログインします。直接開いたブラウザーとクライアントアプリではIDとパスワードを入力してください。", version:"バージョン",
      launcherPort:"DSMアイコンの外部ポート", launcherPortHint:"公開ホスト名からDSMアイコンを開くときに使用します。LANアクセスでは引き続き8791番ポートを使用します。", saveLauncherPort:"アイコンポートを保存", launcherPortSaved:"DSMアイコンは外部ポート{port}を使用します。",
      downloadMethod:"ファイルごとのダウンロード方式", downloadMethodHint:"単一接続では分割・結合を省略し、共通の整合性検証は維持します。", method:"方式", segmentedMode:"8分割ダウンロード + 検証", singleMode:"単一接続 + 検証",
      singleModeWarningTitle:"単一接続の注意点", singleModeWarning:"1接続でサービスへの要求負荷を下げます。完了ファイルのサイズとハッシュは引き続き検証するため、検証中のディスク読み取りは発生します。", saveDownloadMethod:"ダウンロード方式を保存", singleModeShort:"単一接続", segmentedModeShort:"8分割 + 検証",
      sponsorTitle:"NASDropを支援", sponsorHint:"NASDropがお役に立った場合は、GitHub Sponsorsで継続的な開発を支援できます。", sponsorAction:"GitHubで支援する",
      folderTitle:"保存先フォルダーを選択", close:"閉じる", up:"上へ", cancel:"キャンセル", chooseThisFolder:"このフォルダーを選択", requestFailed:"リクエストを処理できませんでした。",
      statusQueued:"待機中", statusReady:"準備完了", statusDownloading:"ダウンロード中", statusWaitingProcessing:"ディスク処理待ち", statusVerifying:"検証中", statusExtracting:"展開中", statusPublishing:"保存先へ移動中", statusPasswordRequired:"パスワードが必要", statusPaused:"一時停止", statusCompleted:"完了", statusFailed:"エラー", statusCancelled:"停止済み",
      writable:"書き込み可", permissionRequired:"権限が必要", notSelected:"未選択", packageWritable:"パッケージアカウントで書き込み可", dedicatedAccount:"パッケージ専用アカウント",
      gofileCooldown:"GoFile保護待機中 · {time}以降に自動再開します。繰り返し試行しないでください。", sameServiceSummary:"同一サービス最大{count}件", qrAlt:"NASDropクライアント接続QR", qrFailed:"QRを作成できません: {error}",
      processing:"{count}件処理中", noQueuedJobs:"待機中のジョブはありません", noJobsTitle:"ダウンロードジョブはありません。", noJobsHint:"リンクを追加すると、ここで進行状況を管理できます。", scheduled:"予約待機", integrity:"ファイル検証情報",
      confirmDelete:"選択した{count}件のジョブ履歴を削除しますか？", inspectLink:"リンクを確認中…", addedMany:"{count}ファイルを{target}のキューに追加しました。", addedOne:"{name}を{target}のキューに追加しました。",
      confirmClear:"完了した{count}件のジョブ履歴をすべて削除しますか？", confirmParallel:"同一サービスのジョブを最大{count}件同時実行しますか？速度制限やNAS負荷が増える場合があります。", saving:"保存中…",
      parallelSaved:"同一サービスのジョブを最大{count}件同時実行するよう設定しました。", sequentialSaved:"同一サービスのジョブは1件ずつ実行します。", loadingFolders:"フォルダーを読み込み中…",
      confirmSingleMode:"単一接続ダウンロードを使用しますか？サービスへの要求負荷を下げつつ、最終整合性検証は維持されます。", singleModeSaved:"新規および再開ジョブは単一接続と最終整合性検証を使用します。", segmentedModeSaved:"新規および再開ジョブは8分割ダウンロードと完全検証を使用します。",
      currentWritable:"このフォルダーに保存できます。", currentNotWritable:"この場所は選択できません。書き込み可能なサブフォルダーを選択してください。", browse:"開く", noSubfolders:"表示できるサブフォルダーはありません。",
      processingTitle:"一時フォルダーと展開", processingHint:"分割ファイルは非表示の作業領域でダウンロード・結合され、完成した結果だけが保存先に表示されます。", temporaryFolder:"一時フォルダー", archiveEngine:"展開エンジン", engineReady:"7-Zip準備完了", engineMissing:"エンジンなし", autoExtract:"新規ジョブの展開を既定にする", diskProtection:"ディスク処理中は新規ダウンロードを一時停止", archiveFormats:"ZIP、AES ZIP、7z、RAR、TAR系をアーカイブ名のフォルダーに展開します。", saveProcessing:"処理設定を保存", autoExtractOn:"既定の展開オン", autoExtractOff:"既定の展開オフ", processingSavedOn:"新規ジョブは展開が既定で、ジョブごとに変更できます。", processingSavedOff:"新規ジョブはアーカイブ保持が既定です。", archiveExtracted:"展開完了 · 元のアーカイブは一時領域でのみ使用", extractThisJob:"ダウンロード後に展開", archivePasswordOptional:"アーカイブのパスワード（任意）", archivePassword:"アーカイブのパスワード", retryExtraction:"展開を再試行",
      defaultChanged:"既定の保存先を{target}に変更しました。"
    },
    zh: {
      language:"语言", loginHint:"请使用在此NAS上设置的NASDrop ID和密码登录。从DSM图标打开时会自动登录。", username:"ID", password:"密码", openDashboard:"打开控制面板", accountNotConfigured:"尚未设置账户。请从DSM图标打开NASDrop，并先创建ID和密码。", logout:"退出登录",
      dashboard:"控制面板", settings:"设置", runningOnNas:"正在NAS上运行", downloads:"下载", linkLabel:"GigaFile、GoFile或Pixeldrain下载链接", downloadNow:"下载到NAS",
      destination:"保存位置", checking:"正在检查…", checkingShort:"检查中", chooseFolder:"选择文件夹", jobs:"任务列表", loading:"正在加载…", clearCompleted:"清除已完成项",
      selected:"已选择{count}项", selectAll:"全选", clearSelection:"取消选择", pause:"暂停", resume:"继续", delete:"删除",
      clientConnection:"客户端连接", accountHint:"直接打开的浏览器和客户端应用使用此ID和密码登录。DSM图标仍会自动登录。", currentPassword:"当前密码", newPassword:"新密码", confirmPassword:"确认新密码", passwordRules:"请输入10至128个字符。系统不会保存密码原文，只保存加盐哈希。", saveAccount:"保存ID和密码", resetAccount:"重新设置", resetAccountHint:"请输入新的ID和密码后保存。现有客户端会话将全部退出。", passwordMismatch:"两次输入的新密码不一致。", accountSaved:"已保存客户端登录ID和密码。",
      defaultFolder:"默认保存位置", defaultFolderHint:"未另选文件夹时，任务将保存到此位置。", change:"更改", parallelTitle:"同一服务并行下载",
      parallelHint:"默认关闭。启用后，可同时启动GoFile等同一服务的多个任务。", allowParallel:"允许并行下载", sameServiceMax:"每个服务的最大数量",
      twoJobs:"2项", threeJobs:"3项", warning:"注意", parallelWarning:"在8段模式下，每个任务最多使用8个连接。3个活动任务最多会产生24个连接，可能增加限速、临时封禁以及NAS的CPU、磁盘和网络负载。",
      off:"关闭", saveParallel:"保存并行下载设置", folderPermissions:"文件夹权限", folderPermissionsHint:"无权访问的共享文件夹会显示为锁定。请在DSM共享文件夹权限中，向此套件的内部系统用户授予读写权限。",
      serviceAccount:"服务账户", serviceAddress:"服务地址", serviceAddressHint:"连接的客户端使用此地址以及已设置的ID和密码。", accessMethodHint:"DSM图标会自动登录。直接打开的浏览器和客户端应用必须输入ID和密码。", version:"版本",
      launcherPort:"DSM 图标外部端口", launcherPortHint:"通过公共主机名打开 DSM 图标时使用。局域网访问仍使用 8791 端口。", saveLauncherPort:"保存图标端口", launcherPortSaved:"DSM 图标将使用外部端口 {port}。",
      downloadMethod:"单个文件下载方式", downloadMethodHint:"单连接会跳过分段和合并，同时保留统一的完整性验证。", method:"方式", segmentedMode:"8段下载 + 验证", singleMode:"单连接 + 验证",
      singleModeWarningTitle:"单连接注意事项", singleModeWarning:"单个连接可降低服务请求压力。完成文件仍会检查大小和哈希，因此验证期间仍会读取磁盘。", saveDownloadMethod:"保存下载方式", singleModeShort:"单连接", segmentedModeShort:"8段 + 验证",
      sponsorTitle:"支持NASDrop", sponsorHint:"如果NASDrop对您有帮助，可以通过GitHub Sponsors支持项目的持续开发。", sponsorAction:"在GitHub上支持",
      folderTitle:"选择保存文件夹", close:"关闭", up:"上一级", cancel:"取消", chooseThisFolder:"选择此文件夹", requestFailed:"无法完成请求。",
      statusQueued:"等待中", statusReady:"准备就绪", statusDownloading:"下载中", statusWaitingProcessing:"等待磁盘处理", statusVerifying:"验证中", statusExtracting:"正在解压", statusPublishing:"正在移至保存位置", statusPasswordRequired:"需要密码", statusPaused:"已暂停", statusCompleted:"已完成", statusFailed:"错误", statusCancelled:"已停止",
      writable:"可写", permissionRequired:"需要权限", notSelected:"未选择", packageWritable:"套件账户可写", dedicatedAccount:"套件专用账户",
      gofileCooldown:"GoFile保护等待中 · 将在{time}后自动恢复。请勿反复重试。", sameServiceSummary:"同一服务最多{count}项", qrAlt:"NASDrop客户端连接二维码", qrFailed:"无法生成二维码：{error}",
      processing:"正在处理{count}项", noQueuedJobs:"没有等待中的任务", noJobsTitle:"没有下载任务。", noJobsHint:"添加链接后可在此管理进度。", scheduled:"计划等待", integrity:"文件验证信息",
      confirmDelete:"要删除所选的{count}条任务记录吗？", inspectLink:"正在检查链接…", addedMany:"已将{count}个文件添加到{target}队列。", addedOne:"已将{name}添加到{target}队列。",
      confirmClear:"要删除全部{count}条已完成任务记录吗？", confirmParallel:"要同时运行最多{count}个同一服务的任务吗？限速风险和NAS负载可能增加。", saving:"正在保存…",
      parallelSaved:"已设置同一服务最多并行运行{count}个任务。", sequentialSaved:"同一服务的任务将逐个运行。", loadingFolders:"正在加载文件夹…",
      confirmSingleMode:"要使用单连接下载吗？这会降低服务请求压力，同时保留最终完整性验证。", singleModeSaved:"新建和继续的任务将使用单连接和最终完整性验证。", segmentedModeSaved:"新建和继续的任务将使用8段下载和完整验证。",
      currentWritable:"可以保存到当前文件夹。", currentNotWritable:"无法选择当前位置。请选择可写的子文件夹。", browse:"浏览", noSubfolders:"没有可显示的子文件夹。",
      processingTitle:"临时文件夹和解压", processingHint:"分片在隐藏工作区中下载并合并，保存位置只显示完整结果。", temporaryFolder:"临时文件夹", archiveEngine:"解压引擎", engineReady:"7-Zip已就绪", engineMissing:"缺少引擎", autoExtract:"新任务默认解压", diskProtection:"磁盘处理期间暂停新下载", archiveFormats:"ZIP、AES ZIP、7z、RAR和TAR系列会解压到同名文件夹。", saveProcessing:"保存处理设置", autoExtractOn:"默认解压开启", autoExtractOff:"默认解压关闭", processingSavedOn:"新任务默认解压，并可逐任务更改。", processingSavedOff:"新任务默认保留压缩文件。", archiveExtracted:"解压完成 · 原压缩文件仅在临时空间中使用", extractThisJob:"下载后解压", archivePasswordOptional:"压缩密码（可选）", archivePassword:"压缩密码", retryExtraction:"重试解压",
      defaultChanged:"默认保存位置已更改为{target}。"
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
