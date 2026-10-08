// The module must be named "Bodycam" so its classes load as /Script/Bodycam.<Class>, like the game's.
using UnrealBuildTool;

public class Bodycam : ModuleRules
{
	public Bodycam(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "GameplayTags", "UMG", "HostMigrationSystem" });
	}
}
