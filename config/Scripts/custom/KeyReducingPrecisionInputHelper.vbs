Option Explicit

Dim shell
Dim processId

If WScript.Arguments.Count < 1 Then
    WScript.Quit 1
End If

processId = CLng(WScript.Arguments(0))
Set shell = CreateObject("WScript.Shell")

If Not shell.AppActivate(processId) Then
    WScript.Quit 2
End If

WScript.Sleep 180
shell.SendKeys "^a"
WScript.Sleep 140
shell.SendKeys "0"
WScript.Sleep 140
shell.SendKeys "."
WScript.Sleep 140
shell.SendKeys "7"
WScript.Sleep 140
shell.SendKeys "{ENTER}"
WScript.Sleep 180

WScript.Quit 0
