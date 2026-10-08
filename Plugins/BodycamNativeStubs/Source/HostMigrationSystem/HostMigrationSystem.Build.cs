// The module must be named "HostMigrationSystem" so its classes load as /Script/HostMigrationSystem.<Class>, like the game's.
using UnrealBuildTool;

public class HostMigrationSystem : ModuleRules
{
	public HostMigrationSystem(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
	}
}
