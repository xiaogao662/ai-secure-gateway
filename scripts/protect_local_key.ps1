# Run only after the owner SID has been confirmed. Never reads key contents.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OwnerSid,
    [Parameter(Mandatory=$true)][string]$BackupName
)
$ErrorActionPreference = 'Stop'
$projectPath = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$keyDirectory = Join-Path $projectPath '.secrets'
$keyPath = Join-Path $keyDirectory 'application.key'
$backupRoot = Join-Path $projectPath '.acl-backups'
if ($BackupName -notmatch '^[a-zA-Z0-9-]+$') { throw 'Invalid backup name' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script with Windows administrator approval.'
}
$owner = [Security.Principal.SecurityIdentifier]::new($OwnerSid)
$null = $owner.Translate([Security.Principal.NTAccount])
foreach ($target in @($projectPath, $keyDirectory, $keyPath)) {
    $item = Get-Item -LiteralPath $target -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked path: $target" }
}
$children = @(Get-ChildItem -LiteralPath $keyDirectory -Force)
if ($children.Count -ne 1 -or $children[0].FullName -ne $keyPath) {
    throw 'Unexpected secrets directory contents; review before changing permissions.'
}
if (Test-Path -LiteralPath $backupRoot) {
    if ((Get-Item -LiteralPath $backupRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Backup path must not be a link' }
} else { $null = New-Item -ItemType Directory -Path $backupRoot }
$backupPath = Join-Path $backupRoot "$BackupName.xml"
$resultPath = Join-Path $backupRoot "$BackupName-result.xml"
if ((Test-Path -LiteralPath $backupPath) -or (Test-Path -LiteralPath $resultPath)) { throw 'Backup already exists; use a new name' }
$before = foreach ($target in @($keyPath, $keyDirectory)) {
    $acl = Get-Acl -LiteralPath $target
    [pscustomobject]@{Path=$target; Sddl=$acl.Sddl}
}
# Contains only paths and permission descriptors, not the encryption key.
$before | Export-Clixml -LiteralPath $backupPath
$allowedSids = @($OwnerSid, 'S-1-5-18', 'S-1-5-32-544')
try {
    foreach ($target in @($keyPath, $keyDirectory)) {
        $directory = $target -eq $keyDirectory
        if ($directory) { $acl = [Security.AccessControl.DirectorySecurity]::new() }
        else { $acl = [Security.AccessControl.FileSecurity]::new() }
        $acl.SetAccessRuleProtection($true, $false)
        $acl.SetOwner($owner)
        $inheritance = [Security.AccessControl.InheritanceFlags]::None
        if ($directory) { $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit' }
        foreach ($sid in $allowedSids) {
            $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                [Security.Principal.SecurityIdentifier]::new($sid),
                [Security.AccessControl.FileSystemRights]::FullControl,
                $inheritance, [Security.AccessControl.PropagationFlags]::None,
                [Security.AccessControl.AccessControlType]::Allow
            )
            $null = $acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $target -AclObject $acl
    }
    foreach ($target in @($keyPath, $keyDirectory)) {
        $acl = Get-Acl -LiteralPath $target
        if (-not $acl.AreAccessRulesProtected) { throw 'Inheritance remains enabled' }
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $OwnerSid) { throw 'Owner verification failed' }
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        if ($rules.Count -ne 3) { throw 'Unexpected access rules' }
        foreach ($rule in $rules) {
            if ($rule.IdentityReference.Value -notin $allowedSids -or $rule.IsInherited -or
                $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl') { throw 'Permission verification failed' }
        }
    }
    [pscustomobject]@{Status='Protected';OwnerSid=$OwnerSid;AllowedSids=$allowedSids;Targets=@($keyDirectory,$keyPath);Backup=$backupPath} | Export-Clixml -LiteralPath $resultPath
} catch {
    $problem = $_.Exception.Message
    $rollbackErrors = @()
    foreach ($entry in $before) {
        try {
            $acl = Get-Acl -LiteralPath $entry.Path
            $acl.SetSecurityDescriptorSddlForm($entry.Sddl)
            Set-Acl -LiteralPath $entry.Path -AclObject $acl
        } catch { $rollbackErrors += $_.Exception.Message }
    }
    [pscustomobject]@{Status='Failed';Error=$problem;RollbackErrors=$rollbackErrors;Backup=$backupPath} | Export-Clixml -LiteralPath $resultPath
    throw
}
