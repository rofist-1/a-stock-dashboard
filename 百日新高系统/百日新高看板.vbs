' 百日新高教学看板 - 启动器
' 双击启动服务器 (无黑框) + 自动打开浏览器

Dim shell, fso, currentDir
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

' 后台启动 Python 服务器 (隐藏窗口)
shell.Run "python run_server.py", 0, False

' 等待服务器启动
WScript.Sleep 2000

' 打开浏览器访问看板
shell.Run "http://localhost:8080/百日新高教学看板.html"

' 弹出提示 (可选)
' MsgBox "百日新高看板已启动!" & vbCrLf & "关闭此窗口不会影响服务器。" & vbCrLf & "如需停止服务器，请运行「停止服务器.vbs」", vbInformation, "百日新高看板"

Set shell = Nothing
Set fso = Nothing
