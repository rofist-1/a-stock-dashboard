' 百日新高教学看板 - 停止服务器
' 双击停止后台运行的 Python 服务器

Dim shell
Set shell = CreateObject("WScript.Shell")

' 终止所有 python.exe 进程
shell.Run "taskkill /f /im python.exe", 0, True

' 确认
MsgBox "服务器已停止。", vbInformation, "百日新高看板"

Set shell = Nothing
