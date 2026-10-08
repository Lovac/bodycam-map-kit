using UnrealBuildTool;

public class BodycamSandboxTarget : TargetRules
{
	public BodycamSandboxTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("BodycamSandbox");
	}
}
