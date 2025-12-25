Set oShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Получаем путь к папке со скриптом
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Переходим в папку со скриптом
oShell.CurrentDirectory = scriptPath

' Пытаемся запустить с py launcher
On Error Resume Next

' Проверяем requests и при необходимости ставим зависимости
cmd = "py -3 -c ""import requests"""
result = oShell.Run(cmd, 0, True)

If result <> 0 Then
    Err.Clear
    cmd = "python -c ""import requests"""
    result = oShell.Run(cmd, 0, True)
End If

If result <> 0 Then
    Err.Clear
    cmd = "py -3 -m pip install -r """ & scriptPath & "\channel_requirements.txt"""
    result = oShell.Run(cmd, 1, True)

    If result <> 0 Then
        Err.Clear
        cmd = "python -m pip install -r """ & scriptPath & "\channel_requirements.txt"""
        result = oShell.Run(cmd, 1, True)
    End If
End If

' Вариант 1: py -3 pythonw
cmd = "py -3 -m pyw """ & scriptPath & "\youtube_channel_collector.py"""
result = oShell.Run(cmd, 0, False)

If Err.Number <> 0 Then
    Err.Clear
    
    ' Вариант 2: pythonw
    cmd = "pythonw """ & scriptPath & "\youtube_channel_collector.py"""
    result = oShell.Run(cmd, 0, False)
    
    If Err.Number <> 0 Then
        Err.Clear
        
        ' Вариант 3: python (с консолью, если pythonw недоступен)
        cmd = "python """ & scriptPath & "\youtube_channel_collector.py"""
        result = oShell.Run(cmd, 1, False)
        
        If Err.Number <> 0 Then
            MsgBox "Ошибка запуска Python!" & vbCrLf & vbCrLf & _
                   "Установите Python с python.org", _
                   vbCritical, "Ошибка"
        End If
    End If
End If

On Error Goto 0

Set oShell = Nothing
Set fso = Nothing
