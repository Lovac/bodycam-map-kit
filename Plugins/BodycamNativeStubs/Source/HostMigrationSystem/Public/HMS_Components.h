// Stand-ins for the game's /Script/HostMigrationSystem component classes.
// Parent classes, property names and property types match the game's usmap (Bodycam 5.5.4). No gameplay code.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HMS_Components.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FHMSActorEventSignature);

UCLASS(ClassGroup = (Bodycam), meta = (BlueprintSpawnableComponent))
class HOSTMIGRATIONSYSTEM_API UHMS_ActorComponent : public UActorComponent
{
	GENERATED_BODY()
};

UCLASS(ClassGroup = (Bodycam), meta = (BlueprintSpawnableComponent))
class HOSTMIGRATIONSYSTEM_API UHMS_InterfaceComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintAssignable, Category = "HostMigration")
	FHMSActorEventSignature HMS_PreSaveActor;

	UPROPERTY(BlueprintAssignable, Category = "HostMigration")
	FHMSActorEventSignature HMS_PostLoadActor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HostMigration")
	int64 HMS_ActorID = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HostMigration")
	int32 HMS_Priority = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HostMigration")
	bool HMS_ShouldSerialize = false;
};
