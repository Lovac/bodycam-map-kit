#include "BodycamHardpointStubs.h"

#include "Components/BoxComponent.h"
#include "Components/DecalComponent.h"
#include "Engine/World.h"
#include "UObject/ObjectSaveContext.h"

namespace
{
	// FunctionNameToBind values of HardPointZone_C's ComponentDelegateBinding_0 in the game, also saved in its Paintball_BP.
	FName BeginOverlapFunction()
	{
		return FName(TEXT("BndEvt__HardPointZone_Box_K2Node_ComponentBoundEvent_0_ComponentBeginOverlapSignature__DelegateSignature"));
	}

	FName EndOverlapFunction()
	{
		return FName(TEXT("BndEvt__HardPointZone_Box_K2Node_ComponentBoundEvent_1_ComponentEndOverlapSignature__DelegateSignature"));
	}

	FName CountdownTickFunction()
	{
		return FName(TEXT("BndEvt__HardPointZone_ZoneCountdown_K2Node_ComponentBoundEvent_2_OnCountdownTick__DelegateSignature"));
	}

	template <typename T>
	T* FindNamed(AActor* Actor, FName Name)
	{
		TInlineComponentArray<T*> Components(Actor);
		for (T* Component : Components)
		{
			if (Component && Component->GetFName() == Name)
			{
				return Component;
			}
		}
		return nullptr;
	}

	// The game's construction scripts swap X and Z of the decal's world scale. A cooked game never reruns them, so the
	// level must hold the result: relative scale (0.01*sz/sx, 0.2, 0.2*sx/sz) for root scale (sx, sy, sz), computed from
	// the template scale (0.2, 0.2, 0.01) so every rerun gives the same value.
	void ApplyDecalScale(AActor* Actor, FName DecalName)
	{
		USceneComponent* Root = Actor->GetRootComponent();
		UDecalComponent* Decal = FindNamed<UDecalComponent>(Actor, DecalName);
		if (!Root || !Decal)
		{
			return;
		}
		const FVector S = Root->GetRelativeScale3D();
		if (FMath::IsNearlyZero(S.X) || FMath::IsNearlyZero(S.Y) || FMath::IsNearlyZero(S.Z))
		{
			return;
		}
		const FVector WorldScale(S.X * 0.2, S.Y * 0.2, S.Z * 0.01);
		Decal->SetRelativeScale3D(FVector(WorldScale.Z / S.X, WorldScale.Y / S.Y, WorldScale.X / S.Z));
	}

	// A sparse delegate (the Box overlap events) only accepts a binding whose function exists on the target, and the
	// placeholder Blueprint has none of the game's event functions. So the binding goes straight into the sparse storage
	// and the delegate's bound flag (its only member) is set, which is what the engine does when it loads a saved binding.
	void AddSparseBinding(FSparseDelegate& Sparse, UObject* DelegateOwner, FName DelegateName, UObject* Target, FName Function)
	{
		FScriptDelegate Delegate;
		Delegate.BindUFunction(Target, Function);
		if (FMulticastScriptDelegate* Existing = FSparseDelegateStorage::GetMulticastDelegate(DelegateOwner, DelegateName))
		{
			Existing->AddUnique(Delegate);
		}
		else
		{
			FMulticastScriptDelegate Multicast;
			Multicast.AddUnique(Delegate);
			FSparseDelegateStorage::SetMulticastDelegate(DelegateOwner, DelegateName, MoveTemp(Multicast));
		}
		*reinterpret_cast<bool*>(&Sparse) = true;
	}

	bool IsGameWorld(const AActor* Actor)
	{
		const UWorld* World = Actor->GetWorld();
		return World && World->IsGameWorld();
	}
}

void ABodycamHardPointZonePreview::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyDecalScale(this, TEXT("BombZoneDecalActual"));
}

ABodycamHardpointZone::ABodycamHardpointZone(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Same names as the game's native subobjects Default__HardPointZone_C.ZoneCountdown and .HMSInterfaceComponent.
	ZoneCountdown = CreateDefaultSubobject<UCountdownComponent>(TEXT("ZoneCountdown"));
	HMSInterfaceComponent = CreateDefaultSubobject<UHMS_InterfaceComponent>(TEXT("HMSInterfaceComponent"));
}

void ABodycamHardpointZone::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyDecalScale(this, TEXT("Decal"));
	AddEditorBindings();
}

void ABodycamHardpointZone::PreSave(FObjectPreSaveContext SaveContext)
{
	Super::PreSave(SaveContext);
	AddEditorBindings();
}

void ABodycamHardpointZone::AddEditorBindings()
{
	if (IsGameWorld(this) || HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject))
	{
		return;
	}
	if (UBoxComponent* Box = FindNamed<UBoxComponent>(this, TEXT("Box")))
	{
		AddSparseBinding(Box->OnComponentBeginOverlap, Box, TEXT("OnComponentBeginOverlap"), this, BeginOverlapFunction());
		AddSparseBinding(Box->OnComponentEndOverlap, Box, TEXT("OnComponentEndOverlap"), this, EndOverlapFunction());
	}
	if (ZoneCountdown)
	{
		FScriptDelegate Tick;
		Tick.BindUFunction(this, CountdownTickFunction());
		ZoneCountdown->OnTick.AddUnique(Tick);
	}
}

void ABodycamHardpointZone::PostInitializeComponents()
{
	Super::PostInitializeComponents();
	// Play in Editor copies the saved bindings, and this placeholder has none of those functions: drop them first.
	if (!IsGameWorld(this))
	{
		return;
	}
	if (UBoxComponent* Box = FindNamed<UBoxComponent>(this, TEXT("Box")))
	{
		Box->OnComponentBeginOverlap.Remove(this, BeginOverlapFunction());
		Box->OnComponentEndOverlap.Remove(this, EndOverlapFunction());
	}
	if (ZoneCountdown)
	{
		ZoneCountdown->OnTick.Remove(this, CountdownTickFunction());
	}
}

FString ABodycamHardpointZone::DescribeBindings()
{
	FString Out;
	if (UBoxComponent* Box = FindNamed<UBoxComponent>(this, TEXT("Box")))
	{
		Out += FString::Printf(TEXT("Box begin overlap %s, end overlap %s"),
			Box->OnComponentBeginOverlap.Contains(this, BeginOverlapFunction()) ? TEXT("bound") : TEXT("MISSING"),
			Box->OnComponentEndOverlap.Contains(this, EndOverlapFunction()) ? TEXT("bound") : TEXT("MISSING"));
	}
	else
	{
		Out += TEXT("no Box");
	}
	Out += FString::Printf(TEXT(" | ZoneCountdown tick %s"),
		ZoneCountdown && ZoneCountdown->OnTick.Contains(this, CountdownTickFunction()) ? TEXT("bound") : TEXT("MISSING"));
	return Out;
}

FString UBodycamStubsLibrary::DescribeHardpointBindings(AActor* Zone)
{
	ABodycamHardpointZone* HardpointZone = Cast<ABodycamHardpointZone>(Zone);
	return HardpointZone ? HardpointZone->DescribeBindings() : FString(TEXT("not a hardpoint zone"));
}
