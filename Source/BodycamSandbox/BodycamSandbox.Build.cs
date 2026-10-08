// Empty primary module. A project with a code plugin needs one on an installed engine.
using UnrealBuildTool;

public class BodycamSandbox : ModuleRules
{
	public BodycamSandbox(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
	}
}
