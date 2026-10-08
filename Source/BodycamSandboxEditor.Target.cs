using UnrealBuildTool;

public class BodycamSandboxEditorTarget : TargetRules
{
	public BodycamSandboxEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("BodycamSandbox");
		ExtraModuleNames.Add("BotsCoordAuthoring");   // editor-only bot logic authoring tool (26 Sep 2026)
	}
}
